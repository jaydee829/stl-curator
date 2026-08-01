from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path

import frontmatter

from stl_curator.config import Config
from stl_curator.grouping import ModelGroup
from stl_curator.meshfacts import MeshFacts

MACHINE_FIELDS = {
    "id",
    "thumb",
    "thumbs_all",
    "height_mm",
    "group_confidence",
    "mesh_error",
    "paths_root",
    "type",
}
HUMAN_FIELDS = {"status", "tags", "title", "creator", "campaign", "assembly", "source", "mmf_id"}


def merge_files_list(existing, generated, prior_hashes: set[str] | frozenset[str] = frozenset()):
    """Merge existing (human-visible) file entries with freshly generated ones.

    Matches each existing entry to a generated entry preferring an exact path
    match, falling back to a hash match (rename tracking). Path-first matching
    is required so that two members sharing an identical content hash (e.g.
    duplicate files) each keep their own entry instead of both collapsing onto
    whichever generated entry the naive hash lookup found first.

    `prior_hashes` is the group's previously-cached member hash set. A leftover
    generated entry (one with no matching existing entry) whose hash is in
    `prior_hashes` is a file the human explicitly removed from this note's
    `files:` list on a prior run — it must NOT be silently re-added. A
    leftover generated entry whose hash is NOT in `prior_hashes` is genuinely
    new (never seen in this group before) and is appended as before.
    """
    existing = existing or []
    remaining = list(generated)

    def _pop_match(pred):
        for i, g in enumerate(remaining):
            if pred(g):
                return remaining.pop(i)
        return None

    out = []
    existing_hashes = {e["hash"] for e in existing}
    for e in existing:
        gen = _pop_match(lambda g, path=e["path"]: g["path"] == path)
        if gen is None:
            gen = _pop_match(lambda g, hash_=e["hash"]: g["hash"] == hash_)
        entry = dict(e)
        if gen is not None:
            entry["path"] = gen["path"]  # machine fact
            entry["hash"] = gen["hash"]  # machine fact
            # Footprint is machine-owned: generated wins when present, existing preserved when absent
            if "footprint" in gen:
                entry["footprint"] = gen["footprint"]
        out.append(entry)
    kept_new = [
        dict(g)
        for g in remaining
        if not (g["hash"] in prior_hashes and g["hash"] not in existing_hashes)
    ]
    out.extend(sorted(kept_new, key=lambda g: g["path"]))
    return out


def merge_frontmatter(
    existing: dict | None,
    generated: dict,
    prior_hashes: set[str] | frozenset[str] = frozenset(),
) -> dict:
    if existing is None:
        return copy.deepcopy(generated)
    merged = copy.deepcopy(existing)  # deep copy to avoid aliasing nested mutables
    for k, v in generated.items():
        if k == "files":
            merged["files"] = merge_files_list(existing.get("files"), v, prior_hashes)
        elif k in MACHINE_FIELDS:
            merged[k] = v
        elif k in HUMAN_FIELDS:
            if k not in existing:
                merged[k] = v
        else:
            merged.setdefault(k, v)
    # Clear stale machine fields (present in existing but absent from generated)
    for field in MACHINE_FIELDS:
        if field in merged and field not in generated:
            del merged[field]
    return merged


def slugify(text: str) -> str:
    s = re.sub(r"[ _]+", "-", text.strip().lower())
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-")


def _slug_or_hash(text: str) -> str:
    """Convert text to slug; if empty, use hash fallback for unicode-only text.

    Returns slugified text or "u" + first 8 hex digits of SHA256(utf-8 encoded text).
    """
    slug = slugify(text)
    if slug:
        return slug
    return "u" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def note_path(vault_dir: Path, creator: str, title: str) -> Path:
    """Compute canonical path for a model note.

    Handles unicode-only names by using hash fallback for empty slugs,
    preventing collisions when creator or title contains only non-ASCII characters.
    """
    creator_slug = _slug_or_hash(creator)
    title_slug = _slug_or_hash(title)
    return vault_dir / "models" / f"{creator_slug}--{title_slug}.md"


def resolve_note_path(
    vault_dir: Path,
    creator: str,
    title: str,
    group_id: str,
    member_hashes: set[str] | frozenset[str] = frozenset(),
) -> Path:
    """Resolve note path, handling collisions with different groups.

    Returns the canonical path for a model group's note. If a note file exists
    with a different group id, returns a disambiguated path with the group_id appended.
    If the disambiguated path also exists with yet another group id, still returns it
    (ids are content-derived, so collisions indicate the same group).

    `group_id` is a hash of the *current* member set, so it changes whenever a
    file joins or leaves the folder cluster (by design — see group identity
    stability spec). A raw id mismatch alone can therefore mean either (a) an
    unrelated group that happens to share this creator/title, or (b) the same
    model that simply gained or lost a member since the note was last written.
    `member_hashes`, when provided, disambiguates the two: any overlap with the
    existing note's own files means it's the same evolving model, so the note
    is reused (and its stale id refreshed via the machine-owned "id" field)
    instead of forking a duplicate note.

    Malformed frontmatter in an existing note is treated as a collision (id treated as
    UNKNOWN), and the id-suffixed path is returned without raising an exception.
    """
    base_path = note_path(vault_dir, creator, title)

    # If file doesn't exist, use base path
    if not base_path.exists():
        return base_path

    # Load existing note, treating malformed YAML as a collision
    try:
        existing_note = frontmatter.load(base_path)
        existing_id = existing_note.metadata.get("id")
        existing_hashes = {
            f["hash"] for f in (existing_note.metadata.get("files") or []) if "hash" in f
        }
    except Exception:  # noqa: BLE001
        # Malformed frontmatter: treat as collision, never merge into unreadable note
        existing_id = None
        existing_hashes = set()

    # If existing note has the same id, it's our file
    if existing_id == group_id:
        return base_path

    # Same evolving model (shares at least one member with the existing note),
    # not an unrelated group that happens to collide on creator/title
    if member_hashes and existing_hashes & member_hashes:
        return base_path

    # Collision (different id or malformed): return disambiguated path with group_id
    creator_slug = _slug_or_hash(creator)
    title_slug = _slug_or_hash(title)

    return vault_dir / "models" / f"{creator_slug}--{title_slug}--{group_id}.md"


def infer_creator_campaign(rel_path: str) -> tuple[str, str | None]:
    parts = Path(rel_path).parts
    creator = parts[0] if parts else "Unknown"
    campaign = parts[1] if len(parts) >= 3 else None
    return creator, campaign


_SOURCE_RE = re.compile(r"(patreon|kickstarter|mmf)", re.IGNORECASE)


def build_frontmatter(
    group: ModelGroup,
    cfg: Config,
    facts_by_hash: dict[str, MeshFacts],
    thumb_rel: str | None,
    footprints_dir_name: str = "footprints",
) -> dict:
    first_rel = group.members[0].record.rel_path
    creator, campaign = infer_creator_campaign(first_rel)
    files = []
    heights, any_err = [], False
    for m in group.members:
        h = m.record.hash
        facts = facts_by_hash.get(h)
        if facts:
            any_err = any_err or bool(facts.error)
            if facts.height_mm is not None:
                heights.append(facts.height_mm)
        files.append(
            {
                "path": m.record.rel_path,
                "hash": h,
                "role": m.role,
                "footprint": f"{footprints_dir_name}/{h[:2]}/{h}.json",
            }
        )
    src = _SOURCE_RE.search(first_rel)
    review = group.assembly == "needs-review" or group.confidence < cfg.group_confidence_min
    fm = {
        "id": group.id,
        "type": "model",
        "title": group.title,
        "creator": f"[[{creator}]]",
        "campaign": f"[[{creator} {campaign}]]" if campaign else None,
        "files": files,
        "assembly": group.assembly,
        "thumb": thumb_rel,
        "thumbs_all": [],
        "height_mm": max(heights) if heights else None,
        "mesh_error": any_err,
        "group_confidence": round(group.confidence, 2),
        "tags": ["needs-review"] if review else [],
        "status": "unprinted",
        "source": src.group(1).lower() if src else "other",
        "mmf_id": None,
        "paths_root": str(cfg.store_root),
    }
    return fm


def write_model_note(
    path: Path,
    generated_fm: dict,
    title: str,
    prior_hashes: set[str] | frozenset[str] = frozenset(),
) -> tuple[str, set[str]]:
    """Write or update a model note, merging machine facts with human edits.

    Returns (status, final_hashes) where status is "created" | "updated" |
    "unchanged" and final_hashes is the resulting note's files hash set
    (after merge) — the caller uses this to detect human divergence from the
    freshly generated group membership.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        note = frontmatter.load(path)
        merged = merge_frontmatter(dict(note.metadata), generated_fm, prior_hashes)
        final_hashes = {f["hash"] for f in merged.get("files", [])}
        if merged == dict(note.metadata):
            return "unchanged", final_hashes
        note.metadata = merged
        with open(path, "w", encoding="utf-8") as f:
            frontmatter.dump(note, f)
        return "updated", final_hashes
    note = frontmatter.Post(
        f"# {title}\n\n> Auto-generated stub. Notes below this line are yours; "
        "the pipeline never touches body text.\n",
        **generated_fm,
    )
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(note, f)
    final_hashes = {f["hash"] for f in generated_fm.get("files", [])}
    return "created", final_hashes


_CREATOR_BODY = """# {name}

## Campaigns
```dataview
LIST FROM "campaigns" WHERE creator = [[{name}]]
```

## Models
```dataview
TABLE thumb, status FROM "models" WHERE creator = [[{name}]]
```
"""

_CAMPAIGN_BODY = """# {name}

## Models
```dataview
TABLE thumb, status FROM "models" WHERE campaign = [[{name}]]
```
"""


def ensure_entity_note(vault_dir: Path, kind: str, name: str, creator: str | None = None) -> bool:
    """Create entity note (creator or campaign) if not present.

    For campaigns, creator must be provided and is used for the frontmatter wikilink.
    Raises ValueError if kind=="campaigns" and creator is None.

    Returns True if created, False if already exists.
    """
    if kind == "campaigns" and creator is None:
        raise ValueError("creator must be provided for campaign entity notes")

    path = vault_dir / kind / f"{name}.md"
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    body = _CREATOR_BODY if kind == "creators" else _CAMPAIGN_BODY
    meta = {"type": "creator" if kind == "creators" else "campaign"}
    if kind == "campaigns":
        meta["creator"] = f"[[{creator}]]"
    note = frontmatter.Post(body.format(name=name), **meta)
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(note, f)
    return True


def plan_model_note(
    path: Path,
    generated_fm: dict,
    prior_hashes: set[str] | frozenset[str] = frozenset(),
) -> str:
    """Predict the write_model_note result without writing anything to disk.

    Used by dry-run ingest to report created/updated/unchanged counts.
    """
    if not path.exists():
        return "created"
    note = frontmatter.load(path)
    merged = merge_frontmatter(dict(note.metadata), generated_fm, prior_hashes)
    return "unchanged" if merged == dict(note.metadata) else "updated"


def write_vault_config(vault_dir: Path) -> None:
    ob = vault_dir / ".obsidian"
    if ob.exists():
        return
    ob.mkdir(parents=True)
    (ob / "app.json").write_text("{}", encoding="utf-8")
    (ob / "community-plugins.json").write_text('["dataview"]', encoding="utf-8")
