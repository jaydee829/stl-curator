from __future__ import annotations

import copy

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
