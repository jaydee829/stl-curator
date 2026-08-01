from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.grouping import ModelGroup, group_folder, load_vocab
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
    claimed = cache.claimed_hashes()

    by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    images_by_folder: dict[str, list[FileRecord]] = defaultdict(list)
    for rec in records:
        folder = str(Path(rec.rel_path).parent)
        if rec.kind == "stl":
            by_folder[folder].append(rec)
        elif rec.kind == "image":
            images_by_folder[folder].append(rec)

    if not dry_run:
        cfg.vault_dir.mkdir(parents=True, exist_ok=True)
        write_vault_config(cfg.vault_dir)

    for folder in sorted(by_folder):
        stls = [r for r in by_folder[folder] if r.hash not in claimed]
        for group in group_folder(stls, vocab, cfg):
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
            npath = resolve_note_path(cfg.vault_dir, creator, group.title, group.id)
            if dry_run:
                result = plan_model_note(npath, fm)
            else:
                result = write_model_note(npath, fm, group.title)
                cache.upsert_group(
                    group.id, [m.record.hash for m in group.members], group.confidence
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

    Clears the cache, rescans the store, and restores all groups from vault notes.
    All vault groups are marked as human_claimed=True since the vault is the
    curated source of truth.

    Args:
        cfg: Configuration containing store_root, vault_dir, and cache_db paths

    Returns:
        Count of notes restored from vault
    """
    cache = Cache(cfg.cache_db)
    cache.clear()
    for rec in scan_store(cfg.store_root):
        cache.upsert_file(rec)
    restored = 0
    models_dir = cfg.vault_dir / "models"
    if models_dir.exists():
        for note_file in sorted(models_dir.glob("*.md")):
            try:
                post = frontmatter.load(note_file)
                fm = post.metadata
            except (OSError, ValueError, KeyError):
                # Corrupt or unparseable note; skip it but continue processing others
                continue
            files = fm.get("files") or []
            if fm.get("id") and files:
                cache.upsert_group(
                    fm["id"],
                    [f["hash"] for f in files],
                    fm.get("group_confidence", 1.0),
                    human_claimed=True,
                )
                restored += 1
    cache.close()
    return restored
