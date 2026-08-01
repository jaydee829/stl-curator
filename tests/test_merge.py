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
