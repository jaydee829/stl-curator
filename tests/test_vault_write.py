from pathlib import Path

import frontmatter
import pytest

from stl_curator.config import Config
from stl_curator.grouping import GroupMember, ModelGroup
from stl_curator.meshfacts import MeshFacts
from stl_curator.scan import FileRecord
from stl_curator.vault import (
    build_frontmatter,
    ensure_entity_note,
    infer_creator_campaign,
    slugify,
    write_model_note,
)


@pytest.mark.parametrize(
    "text,slug",
    [
        ("GoblinCo", "goblinco"),
        ("Owlbear, Large", "owlbear-large"),
        ("troll_king  2", "troll-king-2"),
    ],
)
def test_slugify(text, slug):
    assert slugify(text) == slug


@pytest.mark.parametrize(
    "rel,creator,campaign",
    [
        ("GoblinCo/2024-03/kit/goblin.stl", "GoblinCo", "2024-03"),
        ("GoblinCo/goblin.stl", "GoblinCo", None),
    ],
)
def test_infer_creator_campaign(rel, creator, campaign):
    assert infer_creator_campaign(rel) == (creator, campaign)


def make_group():
    rec = FileRecord("GoblinCo/2024-03/goblin_pose1.stl", Path("x"), "aabbccdd" * 8, 1, 1.0, "stl")
    return ModelGroup([GroupMember(rec, "variant")], "Goblin", "variants", 0.95)


def cfg(tmp_path):
    return Config(
        store_root=tmp_path,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "c.db",
    )


def test_build_frontmatter_schema(tmp_path):
    fm = build_frontmatter(
        make_group(),
        cfg(tmp_path),
        {"aabbccdd" * 8: MeshFacts(30.0, 100, True)},
        thumb_rel="thumbs/xx/x.webp",
    )
    assert fm["type"] == "model"
    assert fm["creator"] == "[[GoblinCo]]"
    assert fm["campaign"] == "[[GoblinCo 2024-03]]"
    assert fm["source"] == "other"
    assert fm["height_mm"] == 30.0
    assert fm["files"][0]["footprint"].startswith("footprints/aa/")
    assert fm["status"] == "unprinted"


def test_build_frontmatter_mesh_error_false(tmp_path):
    """mesh_error must be False when no member has an error."""
    fm = build_frontmatter(
        make_group(),
        cfg(tmp_path),
        {"aabbccdd" * 8: MeshFacts(30.0, 100, True)},
        thumb_rel="thumbs/xx/x.webp",
    )
    assert fm["mesh_error"] is False


def test_build_frontmatter_mesh_error_true(tmp_path):
    """mesh_error must be True when a member has an error."""
    fm = build_frontmatter(
        make_group(),
        cfg(tmp_path),
        {"aabbccdd" * 8: MeshFacts(30.0, 100, True, error="invalid mesh")},
        thumb_rel="thumbs/xx/x.webp",
    )
    assert fm["mesh_error"] is True


def test_write_then_rewrite_unchanged(tmp_path):
    p = tmp_path / "vault" / "models" / "n.md"
    fm = {"id": "g1", "type": "model", "title": "Goblin", "status": "unprinted"}
    assert write_model_note(p, dict(fm), "Goblin") == "created"
    assert write_model_note(p, dict(fm), "Goblin") == "unchanged"


def test_rewrite_preserves_body_and_human_fields(tmp_path):
    p = tmp_path / "vault" / "models" / "n.md"
    write_model_note(p, {"id": "g1", "type": "model", "status": "unprinted"}, "G")
    note = frontmatter.load(p)
    note["status"] = "painted"
    note.content += "\nMy campaign notes."
    with open(p, "w", encoding="utf-8") as f:
        frontmatter.dump(note, f)
    result = write_model_note(
        p, {"id": "g1", "type": "model", "status": "unprinted", "height_mm": 5.0}, "G"
    )
    assert result == "updated"
    out = frontmatter.load(p)
    assert out["status"] == "painted"
    assert out["height_mm"] == 5.0
    assert "My campaign notes." in out.content


def test_entity_note_created_once(tmp_path):
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is True
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is False
    text = (tmp_path / "vault" / "creators" / "GoblinCo.md").read_text(encoding="utf-8")
    assert "dataview" in text and "[[GoblinCo]]" in text
