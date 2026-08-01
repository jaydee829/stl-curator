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
    note_path,
    plan_model_note,
    resolve_note_path,
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
    status, _, _ = write_model_note(p, dict(fm), "Goblin")
    assert status == "created"
    status, _, _ = write_model_note(p, dict(fm), "Goblin")
    assert status == "unchanged"


def test_rewrite_preserves_body_and_human_fields(tmp_path):
    p = tmp_path / "vault" / "models" / "n.md"
    write_model_note(p, {"id": "g1", "type": "model", "status": "unprinted"}, "G")
    note = frontmatter.load(p)
    note["status"] = "painted"
    note.content += "\nMy campaign notes."
    with open(p, "w", encoding="utf-8") as f:
        frontmatter.dump(note, f)
    result, final_hashes, final_paths = write_model_note(
        p, {"id": "g1", "type": "model", "status": "unprinted", "height_mm": 5.0}, "G"
    )
    assert result == "updated"
    assert final_hashes == set()
    assert final_paths == set()
    out = frontmatter.load(p)
    assert out["status"] == "painted"
    assert out["height_mm"] == 5.0
    assert "My campaign notes." in out.content


def test_entity_note_created_once(tmp_path):
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is True
    assert ensure_entity_note(tmp_path / "vault", "creators", "GoblinCo") is False
    text = (tmp_path / "vault" / "creators" / "GoblinCo.md").read_text(encoding="utf-8")
    assert "dataview" in text and "[[GoblinCo]]" in text


@pytest.mark.parametrize(
    "creator,title,expected_slug",
    [
        ("GoblinCo", "Goblin", "goblinco--goblin"),
        ("Owlbear Inc", "Tiny Bear", "owlbear-inc--tiny-bear"),
        ("TrollKing", "troll_king  2", "trollking--troll-king-2"),
    ],
)
def test_note_path_ascii_coverage(tmp_path, creator, title, expected_slug):
    """note_path handles ASCII names correctly."""
    path = note_path(tmp_path / "vault", creator, title)
    assert path.name == f"{expected_slug}.md"
    assert path.parent.name == "models"


@pytest.mark.parametrize(
    "title1,title2",
    [
        ("北京", "東京"),
        ("日本", "中国"),
    ],
)
def test_note_path_unicode_titles_distinct(tmp_path, title1, title2):
    """Unicode-only titles with empty slugs get distinct hash-based names."""
    path1 = note_path(tmp_path / "vault", "Creator", title1)
    path2 = note_path(tmp_path / "vault", "Creator", title2)

    # Both should have hash-based slugs (u + 8 hex chars)
    assert "u" in path1.stem and "u" in path2.stem
    # They should be different
    assert path1 != path2


def test_ensure_entity_note_campaign_requires_creator(tmp_path):
    """ensure_entity_note raises ValueError for campaigns without creator."""
    with pytest.raises(ValueError, match="creator must be provided"):
        ensure_entity_note(tmp_path / "vault", "campaigns", "Titan Forge 2024-03", creator=None)


def test_ensure_entity_note_campaign_with_creator(tmp_path):
    """Campaign entity note uses provided creator name in wikilink."""
    result = ensure_entity_note(
        tmp_path / "vault", "campaigns", "Titan Forge 2024-03", creator="Titan Forge"
    )
    assert result is True
    text = (tmp_path / "vault" / "campaigns" / "Titan Forge 2024-03.md").read_text(encoding="utf-8")
    assert "[[Titan Forge]]" in text
    # Verify it's not using the split hack (which would be [[Titan]])
    assert "[[Titan]]" not in text or "[[Titan Forge]]" in text  # Allow [[Titan Forge]]


def test_ensure_entity_note_campaign_no_creator_wikilink_bug(tmp_path):
    """Campaign with multi-word name doesn't silently use split hack."""
    # This is the bug from FINDING 1: name.split(' ')[0] creates orphaned campaigns
    result = ensure_entity_note(
        tmp_path / "vault", "campaigns", "Titan Forge 2024-03", creator="Titan Forge"
    )
    assert result is True
    text = (tmp_path / "vault" / "campaigns" / "Titan Forge 2024-03.md").read_text(encoding="utf-8")
    # Should have the full creator name, not just "Titan"
    assert "[[Titan Forge]]" in text


def test_resolve_note_path_no_existing_file(tmp_path):
    """resolve_note_path returns base path when file doesn't exist."""
    vault_dir = tmp_path / "vault"
    path = resolve_note_path(vault_dir, "GoblinCo", "Goblin", "group1")
    expected = note_path(vault_dir, "GoblinCo", "Goblin")
    assert path == expected


def test_resolve_note_path_existing_same_id(tmp_path):
    """resolve_note_path returns base path when existing file has same id."""
    vault_dir = tmp_path / "vault"
    base_path = note_path(vault_dir, "GoblinCo", "Goblin")
    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file with group1 id
    fm = {"id": "group1", "type": "model", "title": "Goblin"}
    write_model_note(base_path, fm, "Goblin")

    # Resolve with same id should return base path
    resolved = resolve_note_path(vault_dir, "GoblinCo", "Goblin", "group1")
    assert resolved == base_path


def test_resolve_note_path_existing_different_id(tmp_path):
    """resolve_note_path returns id-suffixed path when existing file has different id."""
    vault_dir = tmp_path / "vault"
    base_path = note_path(vault_dir, "GoblinCo", "Goblin")
    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Create file with group1 id
    fm = {"id": "group1", "type": "model", "title": "Goblin"}
    write_model_note(base_path, fm, "Goblin")

    # Resolve with different id should return suffixed path
    resolved = resolve_note_path(vault_dir, "GoblinCo", "Goblin", "group2")
    assert resolved != base_path
    assert "group2" in resolved.stem
    assert resolved.parent == base_path.parent


@pytest.mark.parametrize(
    "creator1,creator2,title",
    [
        ("北京", "東京", "Goblin"),
        ("日本", "中国", "Model"),
    ],
)
def test_note_path_unicode_creators_distinct(tmp_path, creator1, creator2, title):
    """Unicode-only creators with same title produce distinct paths."""
    path1 = note_path(tmp_path / "vault", creator1, title)
    path2 = note_path(tmp_path / "vault", creator2, title)

    # Both should have hash-based creator slugs
    assert path1.stem != path2.stem
    assert path1 != path2
    # Both should contain hash prefix "u"
    assert "u" in path1.stem
    assert "u" in path2.stem


def test_note_path_unicode_hash_computation(tmp_path):
    """Verify hash computation for unicode text is deterministic and distinct."""
    import hashlib

    # Compute expected hash for 北京
    expected_hash = "u" + hashlib.sha256("北京".encode()).hexdigest()[:8]
    path = note_path(tmp_path / "vault", "北京", "Goblin")

    # Path should contain the hash
    assert expected_hash in path.stem
    assert path.name == f"{expected_hash}--goblin.md"


@pytest.mark.parametrize(
    "existing_fm,generated_fm,expected",
    [
        pytest.param(
            None,
            {"id": "g1", "type": "model", "status": "unprinted"},
            "created",
            id="missing_file",
        ),
        pytest.param(
            {"id": "g1", "type": "model", "status": "unprinted"},
            {"id": "g1", "type": "model", "status": "unprinted"},
            "unchanged",
            id="identical_fm",
        ),
        pytest.param(
            {"id": "g1", "type": "model", "status": "unprinted"},
            {"id": "g1", "type": "model", "status": "unprinted", "height_mm": 5.0},
            "updated",
            id="differing_fm",
        ),
    ],
)
def test_plan_model_note(tmp_path, existing_fm, generated_fm, expected):
    p = tmp_path / "vault" / "models" / "n.md"
    if existing_fm is not None:
        write_model_note(p, dict(existing_fm), "G")
    result = plan_model_note(p, generated_fm)
    assert result == expected
    if expected == "created":
        assert not p.exists()


def test_resolve_note_path_malformed_yaml_no_crash(tmp_path):
    """resolve_note_path handles malformed YAML gracefully without raising."""
    vault_dir = tmp_path / "vault"
    base_path = note_path(vault_dir, "GoblinCo", "Goblin")
    base_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a malformed note with unterminated YAML list
    malformed_content = "---\nid: [unterminated\n---\nBody content here.\n"
    base_path.write_text(malformed_content, encoding="utf-8")

    # resolve_note_path should not crash; should return id-suffixed path
    # (treating malformed file as collision)
    resolved = resolve_note_path(vault_dir, "GoblinCo", "Goblin", "group1")

    # Should return disambiguated path, not raise
    assert resolved != base_path
    assert "group1" in resolved.stem
