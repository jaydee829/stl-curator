import pytest

from stl_curator.vault import merge_files_list, merge_frontmatter

GEN = {
    "id": "g1",
    "type": "model",
    "title": "Goblin",
    "status": "unprinted",
    "tags": ["needs-review"],
    "assembly": "variants",
    "height_mm": 30.0,
    "group_confidence": 0.9,
    "files": [{"path": "C/R/g1.stl", "hash": "h1", "role": "variant"}],
}


def test_no_existing_returns_generated():
    assert merge_frontmatter(None, dict(GEN)) == GEN


@pytest.mark.parametrize(
    "field,human_value",
    [
        ("status", "painted"),
        ("tags", ["goblinoid", "32mm"]),
        ("title", "Goblin Warband"),
        ("assembly", "multipart"),
        ("creator", "[[GoblinCo]]"),
    ],
)
def test_human_fields_survive(field, human_value):
    existing = dict(GEN, **{field: human_value})
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged[field] == human_value


@pytest.mark.parametrize(
    "field,new_value",
    [
        ("height_mm", 99.9),
        ("group_confidence", 0.4),
        ("thumb", "thumbs/g1/new.webp"),
    ],
)
def test_machine_fields_update(field, new_value):
    existing = dict(GEN, thumb="thumbs/old.webp")
    merged = merge_frontmatter(existing, dict(GEN, **{field: new_value}))
    assert merged[field] == new_value


def test_unknown_human_keys_pass_through():
    existing = dict(GEN, my_notes="use for Thornwood")
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged["my_notes"] == "use for Thornwood"


def test_empty_but_set_human_field_survives():
    existing = dict(GEN, tags=[])
    merged = merge_frontmatter(existing, dict(GEN))
    assert merged["tags"] == []


def test_files_role_kept_path_updated():
    existing = [{"path": "old/loc.stl", "hash": "h1", "role": "part"}]
    generated = [{"path": "new/loc.stl", "hash": "h1", "role": "variant"}]
    assert merge_files_list(existing, generated) == [
        {"path": "new/loc.stl", "hash": "h1", "role": "part"}
    ]


def test_files_human_added_member_preserved():
    existing = [
        {"path": "a.stl", "hash": "h1", "role": "model"},
        {"path": "b.stl", "hash": "h2", "role": "part"},
    ]
    generated = [{"path": "a.stl", "hash": "h1", "role": "model"}]
    merged = merge_files_list(existing, generated)
    assert {e["hash"] for e in merged} == {"h1", "h2"}


def test_files_footprint_preserved():
    existing = [
        {"path": "a.stl", "hash": "h1", "role": "model", "footprint": "footprints/h1/h1.json"}
    ]
    generated = [{"path": "a.stl", "hash": "h1", "role": "model"}]
    assert merge_files_list(existing, generated)[0]["footprint"] == "footprints/h1/h1.json"


# FINDING 1: Stale machine fields must clear when absent from generated
def test_machine_field_clears_when_absent_from_generated():
    existing = dict(GEN, mesh_error=True)
    generated = dict(GEN)
    merged = merge_frontmatter(existing, generated)
    assert "mesh_error" not in merged


def test_machine_field_still_updates_when_present_in_generated():
    existing = dict(GEN, mesh_error=False)
    generated = dict(GEN, mesh_error=True)
    merged = merge_frontmatter(existing, generated)
    assert merged["mesh_error"] is True


# FINDING 2: Footprint is machine-owned and refreshes when generated has it
def test_files_footprint_refreshed_when_in_generated():
    existing = [{"path": "a.stl", "hash": "h1", "role": "model", "footprint": "old.json"}]
    generated = [{"path": "a.stl", "hash": "h1", "role": "model", "footprint": "new.json"}]
    assert merge_files_list(existing, generated)[0]["footprint"] == "new.json"


# FINDING 3: Deep copy to avoid aliasing nested mutables
def test_merge_deep_copies_existing_preserves_list_identity():
    existing = dict(GEN, tags=["custom", "tag"])
    merged = merge_frontmatter(existing, dict(GEN))
    # Lists should be equal but not the same object
    assert merged["tags"] == existing["tags"]
    assert merged["tags"] is not existing["tags"]


def test_files_duplicate_hash_entries_stay_paired_by_path():
    """Two members sharing a hash (identical content) must not collapse onto one entry.

    Regression for a convergence bug: naive hash-only matching sent both existing
    entries to whichever generated entry with that hash came first, silently
    dropping one path from the note on every re-merge.
    """
    existing = [
        {"path": "a.stl", "hash": "h1", "role": "model", "footprint": "fp/a.json"},
        {"path": "a_copy.stl", "hash": "h1", "role": "model", "footprint": "fp/a.json"},
    ]
    generated = [
        {"path": "a.stl", "hash": "h1", "role": "model", "footprint": "fp/a.json"},
        {"path": "a_copy.stl", "hash": "h1", "role": "model", "footprint": "fp/a.json"},
    ]
    assert merge_files_list(existing, generated) == existing


# FINDING 4: Deep copy generated when existing is None
def test_merge_deep_copies_generated_when_existing_none():
    generated = dict(GEN, tags=["needs-review"])
    merged = merge_frontmatter(None, generated)
    # Should be equal but not the same object
    assert merged == generated
    assert merged is not generated
    assert merged["tags"] is not generated["tags"]
