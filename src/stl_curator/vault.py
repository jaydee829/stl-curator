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


def merge_files_list(existing, generated):
    existing = existing or []
    out = []
    seen = set()
    for e in existing:
        h = e["hash"]
        gen = next((g for g in generated if g["hash"] == h), None)
        entry = dict(e)
        if gen is not None:
            entry["path"] = gen["path"]  # machine fact
            # Footprint is machine-owned: generated wins when present, existing preserved when absent
            if "footprint" in gen:
                entry["footprint"] = gen["footprint"]
        out.append(entry)
        seen.add(h)
    new = [g for g in generated if g["hash"] not in seen]
    out.extend(sorted((dict(g) for g in new), key=lambda g: g["path"]))
    return out


def merge_frontmatter(existing: dict | None, generated: dict) -> dict:
    if existing is None:
        return copy.deepcopy(generated)
    merged = copy.deepcopy(existing)  # deep copy to avoid aliasing nested mutables
    for k, v in generated.items():
        if k == "files":
            merged["files"] = merge_files_list(existing.get("files"), v)
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


def note_path(vault_dir: Path, creator: str, title: str) -> Path:
    creator_slug = slugify(creator)
    title_slug = slugify(title)

    # Handle unicode-only titles that produce empty slugs
    if not title_slug:
        hash_suffix = "u" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
        title_slug = hash_suffix

    return vault_dir / "models" / f"{creator_slug}--{title_slug}.md"


def resolve_note_path(vault_dir: Path, creator: str, title: str, group_id: str) -> Path:
    """Resolve note path, handling collisions with different groups.

    Returns the canonical path for a model group's note. If a note file exists
    with a different group id, returns a disambiguated path with the group_id appended.
    If the disambiguated path also exists with yet another group id, still returns it
    (ids are content-derived, so collisions indicate the same group).
    """
    base_path = note_path(vault_dir, creator, title)

    # If file doesn't exist or has matching id, use base path
    if not base_path.exists():
        return base_path

    existing_note = frontmatter.load(base_path)
    existing_id = existing_note.metadata.get("id")

    # If existing note has the same id, it's our file
    if existing_id == group_id:
        return base_path

    # Collision: return disambiguated path with group_id
    creator_slug = slugify(creator)
    title_slug = slugify(title)
    if not title_slug:
        title_slug = "u" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]

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


def write_model_note(path: Path, generated_fm: dict, title: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        note = frontmatter.load(path)
        merged = merge_frontmatter(dict(note.metadata), generated_fm)
        if merged == dict(note.metadata):
            return "unchanged"
        note.metadata = merged
        with open(path, "w", encoding="utf-8") as f:
            frontmatter.dump(note, f)
        return "updated"
    note = frontmatter.Post(
        f"# {title}\n\n> Auto-generated stub. Notes below this line are yours; "
        "the pipeline never touches body text.\n",
        **generated_fm,
    )
    with open(path, "w", encoding="utf-8") as f:
        frontmatter.dump(note, f)
    return "created"


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


def write_vault_config(vault_dir: Path) -> None:
    ob = vault_dir / ".obsidian"
    if ob.exists():
        return
    ob.mkdir(parents=True)
    (ob / "app.json").write_text("{}", encoding="utf-8")
    (ob / "community-plugins.json").write_text('["dataview"]', encoding="utf-8")
