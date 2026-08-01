from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.grouping import ModelGroup, Vocab, group_folder, load_vocab
from stl_curator.meshfacts import MeshFacts, extract_mesh_facts
from stl_curator.reports import write_duplicate_report, write_error_report
from stl_curator.scan import FileRecord, scan_store
from stl_curator.thumbs import normalize_to_webp, pick_group_image, render_thumbnail, thumb_path
from stl_curator.vault import (
    build_frontmatter,
    ensure_entity_note,
    infer_creator_campaign,
    plan_model_note,
    resolve_note_path,
    write_model_note,
    write_vault_config,
)
from stl_curator.zips import extract_needed_zips


@dataclass
class IngestSummary:
    files: int = 0
    groups: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    errors: int = 0
    needs_review: int = 0
    thumbs_harvested: int = 0
    thumbs_rendered: int = 0
    thumbs_missing: int = 0


def _mesh_facts_cached(cache: Cache, rec: FileRecord) -> MeshFacts:
    row = cache.get_mesh_facts(rec.hash)
    if row is not None:
        return MeshFacts(
            row["height_mm"],
            row["triangles"],
            None if row["watertight"] is None else bool(row["watertight"]),
            row["error"],
        )
    facts = extract_mesh_facts(rec.abs_path)
    cache.set_mesh_facts(rec.hash, facts.height_mm, facts.triangles, facts.watertight, facts.error)
    return facts


def _ensure_thumb(
    group: ModelGroup,
    images: list[FileRecord],
    cfg: Config,
    cache: Cache,
    dry_run: bool,
    summary: IngestSummary,
) -> str | None:
    dest = thumb_path(cfg.thumbs_dir, group.id)
    rel = f"{cfg.thumbs_dir.name}/{group.id[:2]}/{group.id}.webp"
    if dest.exists():
        return rel
    pick = pick_group_image(images)
    if pick is not None:
        summary.thumbs_harvested += 1
        if not dry_run:
            normalize_to_webp(pick.abs_path, dest)
            cache.set_thumb(group.id, "harvested")
        return rel
    first_stl = group.members[0].record.abs_path
    if dry_run:
        summary.thumbs_rendered += 1  # optimistic count; dry-run doesn't probe GL
        return rel
    if render_thumbnail(first_stl, dest):
        summary.thumbs_rendered += 1
        cache.set_thumb(group.id, "rendered")
        return rel
    summary.thumbs_missing += 1
    cache.set_thumb(group.id, "missing")
    return None


def _compute_groups(records: list[FileRecord], vocab: Vocab, cfg: Config) -> list[ModelGroup]:
    """Compute the machine grouping for a set of scanned records.

    Buckets stl records by containing folder and runs group_folder per folder,
    in folder-sorted order. Shared by ingest and rebuild_cache so their notion
    of "what the machine would group these files into" can never drift apart.
    Non-stl records (images, zips, etc.) are ignored — group_folder only ever
    consumes stl records.
    """
    by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        if rec.kind == "stl":
            folder = str(Path(rec.rel_path).parent)
            by_folder[folder].append(rec)
    groups: list[ModelGroup] = []
    for folder in sorted(by_folder):
        groups.extend(group_folder(by_folder[folder], vocab, cfg))
    return groups


def ingest(cfg: Config, dry_run: bool = False) -> IngestSummary:
    summary = IngestSummary()
    errors: list[tuple[str, str]] = []
    vocab = load_vocab()
    records = scan_store(cfg.store_root)
    if not dry_run:
        zres = extract_needed_zips(records, cfg.store_root)
        errors.extend(zres.errors)
        if zres.extracted:
            records = scan_store(cfg.store_root)
    summary.files = len(records)

    cache = Cache(cfg.cache_db if not dry_run else Path(":memory:"))
    for rec in records:
        cache.upsert_file(rec)
    claimed_paths = cache.claimed_paths()

    images_by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        if rec.kind == "image":
            folder = str(Path(rec.rel_path).parent)
            images_by_folder[folder].append(rec)

    if not dry_run:
        cfg.vault_dir.mkdir(parents=True, exist_ok=True)
        write_vault_config(cfg.vault_dir)

    # Human-diverged (claimed) files are excluded from future regrouping: a
    # file the human has already reassigned/removed must not be reabsorbed
    # into a fresh machine grouping on the next ingest. Scoped by rel_path,
    # not hash: two different physical files can share content (a
    # legitimate cross-folder duplicate) without sharing a location, so
    # excluding by hash would collaterally exclude an unrelated file that
    # merely happens to have the same content.
    unclaimed = [r for r in records if r.rel_path not in claimed_paths]
    for group in _compute_groups(unclaimed, vocab, cfg):
        folder = str(Path(group.members[0].record.rel_path).parent)
        summary.groups += 1
        if group.assembly == "needs-review":
            summary.needs_review += 1
        facts = {m.record.hash: _mesh_facts_cached(cache, m.record) for m in group.members}
        for h, f in facts.items():
            if f.error:
                errors.append(
                    (
                        next(m.record.rel_path for m in group.members if m.record.hash == h),
                        f.error,
                    )
                )
        thumb_rel = _ensure_thumb(
            group, images_by_folder.get(folder, []), cfg, cache, dry_run, summary
        )
        fm = build_frontmatter(
            group, cfg, facts, thumb_rel, footprints_dir_name=cfg.footprints_dir.name
        )
        creator, campaign = infer_creator_campaign(group.members[0].record.rel_path)
        group_hashes = {m.record.hash for m in group.members}
        prior_hashes = cache.group_members(group.id)
        npath = resolve_note_path(
            cfg.vault_dir, creator, group.title, group.id, frozenset(group_hashes), folder
        )
        if dry_run:
            result = plan_model_note(npath, fm, prior_hashes)
        else:
            result, final_hashes, final_paths = write_model_note(
                npath, fm, group.title, prior_hashes
            )
            human_claimed = final_hashes != group_hashes
            cache.upsert_group(
                group.id,
                sorted(final_hashes),
                group.confidence,
                human_claimed=human_claimed,
                member_paths=sorted(final_paths),
            )
            if human_claimed:
                # A hash the group generated but the note no longer carries
                # was removed (or relocated elsewhere) by a human. Tombstone
                # it — keyed by the REMOVED ENTRIES' OWN PATHS, not by hash —
                # so claimed_paths() excludes exactly those physical files
                # from every future regrouping, and nothing else. Keying by
                # hash instead would be wrong: a content-identical duplicate
                # living in a different, untouched folder could share this
                # hash without ever having been removed from its own note,
                # and a hash-global exclusion would collaterally strip it
                # out of its own folder's next regrouping too, fragmenting
                # an otherwise-untouched note. Without this tombstone at
                # all, the removed file would resurface as its own fragment
                # note one ingest later, since it's still physically on disk
                # but isn't a member of any human_claimed group.
                removed_hashes = group_hashes - final_hashes
                if removed_hashes:
                    removed_paths = {f["path"] for f in fm["files"] if f["hash"] in removed_hashes}
                    cache.upsert_group(
                        f"{group.id}-removed",
                        sorted(removed_hashes),
                        1.0,
                        human_claimed=True,
                        member_paths=sorted(removed_paths),
                    )
            ensure_entity_note(cfg.vault_dir, "creators", creator)
            if campaign:
                ensure_entity_note(
                    cfg.vault_dir, "campaigns", f"{creator} {campaign}", creator=creator
                )
        if result == "created":
            summary.created += 1
        elif result == "updated":
            summary.updated += 1
        elif result == "unchanged":
            summary.unchanged += 1

    summary.errors = len(errors)
    if not dry_run:
        write_duplicate_report(cache.duplicate_hashes(), cfg.vault_dir)
        write_error_report(errors, cfg.vault_dir)
    cache.close()
    return summary


def rebuild_cache(cfg: Config) -> int:
    """Rebuild cache from disk and vault frontmatter.

    Clears the cache, rescans the store, and restores group rows from vault
    notes. Divergence-aware: a note is only marked human_claimed=True if its
    files membership actually diverges from what the machine would group the
    same on-disk files into today (computed via the same _compute_groups path
    ingest uses). A note whose membership exactly matches its same-id machine
    group is restored as human_claimed=False, so a subsequent ingest still
    PROCESSES it (rather than freezing it untouched) and can absorb new files
    that land in its folder. A note whose id has no counterpart in the machine
    grouping at all (e.g. the group was hand-edited into something the machine
    would never produce) is, by definition, human-diverged and claimed=True.

    Removal tombstones (see ingest's `"{group.id}-removed"` rows) are not
    persisted anywhere except the cache, so cache loss would otherwise let a
    removed file resurface as its own fragment note. Rebuild re-derives them
    from disk + vault alone: for each machine group with a matching note, any
    hash the machine generated for it that the note doesn't carry AND that
    doesn't appear in ANY vault note (i.e. wasn't relocated into a different,
    already-divergent note) was removed by a human — tombstoned by THAT
    MACHINE ENTRY'S OWN PATH, not by hash. Path-scoping matters here exactly
    as it does in ingest: two machine entries in two different folders can
    share a hash (a legitimate cross-folder duplicate) — tombstoning by hash
    would collaterally exclude the untouched folder's copy from all future
    regrouping too. Keying the tombstone by the specific removed entry's
    path means only that one physical file is ever excluded.

    Args:
        cfg: Configuration containing store_root, vault_dir, and cache_db paths

    Returns:
        Count of notes restored from vault (skipped notes on error not counted)
    """
    cache = Cache(cfg.cache_db)
    try:
        cache.clear()
        records = scan_store(cfg.store_root)
        for rec in records:
            cache.upsert_file(rec)
        vocab = load_vocab()
        # (hash, rel_path) pairs per machine group id — path-aware, since a
        # group can legitimately contain two entries sharing a hash from
        # different physical files (duplicate content within one folder).
        machine_entries_by_id: dict[str, list[tuple[str, str]]] = {
            g.id: [(m.record.hash, m.record.rel_path) for m in g.members]
            for g in _compute_groups(records, vocab, cfg)
        }

        parsed_notes: list[tuple[str, set[str], set[str], float]] = []
        models_dir = cfg.vault_dir / "models"
        if models_dir.exists():
            for note_file in sorted(models_dir.glob("*.md")):
                try:
                    post = frontmatter.load(note_file)
                    fm = post.metadata
                    files = fm.get("files") or []
                    if fm.get("id") and files:
                        note_hashes = {f["hash"] for f in files}
                        note_paths = {f["path"] for f in files}
                        parsed_notes.append(
                            (fm["id"], note_hashes, note_paths, fm.get("group_confidence", 1.0))
                        )
                except Exception:  # noqa: BLE001, S112
                    # Corrupt or unparseable note; skip it but continue processing others
                    # Covers: YAML parsing errors, missing fields, file read errors
                    continue

        # A hash relocated by hand into a different note is already covered:
        # that note's own membership diverges from ITS machine group, so it's
        # restored human_claimed=True below and the hash is claimed via that
        # row's own member_paths. Only a hash absent from every vault note
        # was truly removed and needs a tombstone here.
        all_note_hashes: set[str] = set()
        for _, note_hashes, _, _ in parsed_notes:
            all_note_hashes |= note_hashes

        restored = 0
        for group_id, note_hashes, note_paths, confidence in parsed_notes:
            machine_entries = machine_entries_by_id.get(group_id)
            machine_hashes = (
                {h for h, _ in machine_entries} if machine_entries is not None else None
            )
            human_claimed = machine_hashes is None or note_hashes != machine_hashes
            cache.upsert_group(
                group_id,
                sorted(note_hashes),
                confidence,
                human_claimed=human_claimed,
                member_paths=sorted(note_paths),
            )
            restored += 1
            if machine_entries is not None:
                removed_entries = [
                    (h, p)
                    for h, p in machine_entries
                    if h not in note_hashes and h not in all_note_hashes
                ]
                if removed_entries:
                    cache.upsert_group(
                        f"{group_id}-removed",
                        sorted({h for h, _ in removed_entries}),
                        1.0,
                        human_claimed=True,
                        member_paths=sorted({p for _, p in removed_entries}),
                    )
        return restored
    finally:
        cache.close()
