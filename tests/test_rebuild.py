import frontmatter
import pytest
import trimesh

from stl_curator.cache import Cache
from stl_curator.config import Config
from stl_curator.pipeline import ingest, rebuild_cache


@pytest.fixture
def cfg(tmp_path) -> Config:
    root = tmp_path / "store"
    (root / "C" / "R").mkdir(parents=True)
    trimesh.creation.box(extents=[5, 5, 30]).export(root / "C" / "R" / "orc.stl")
    return Config(
        store_root=root,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "cache.db",
    )


def test_rebuild_restores_unclaimed_when_note_matches_machine(cfg):
    """A note whose files membership exactly matches its same-id machine
    group (no human edits since the last ingest) is restored as
    human_claimed=False — divergence-aware rebuild, not claim-all. The row
    is still restored (n == 1); it's just not in claimed_hashes()."""
    ingest(cfg)
    cfg.cache_db.unlink()  # simulate cache loss
    n = rebuild_cache(cfg)
    assert n == 1
    cache = Cache(cfg.cache_db)
    assert cache.claimed_hashes() == set()
    cache.close()


def test_ingest_after_rebuild_is_noop(cfg):
    """Second ingest after rebuild must still PROCESS the note (not freeze it):
    it should be reported unchanged, not silently skipped. Under the old
    claim-all rebuild, the note's file was excluded from every future folder
    scan entirely, so group_folder was never even called for it — created,
    updated, AND unchanged would all read 0, hiding the freeze as a false
    "noop". Asserting unchanged == the fixture's group count (1: orc.stl)
    proves the note was actually re-evaluated and found identical.
    """
    ingest(cfg)
    cfg.cache_db.unlink()
    rebuild_cache(cfg)
    s = ingest(cfg)
    assert (s.created, s.updated) == (0, 0)
    assert s.unchanged == 1


def test_rebuild_only_claims_diverged_notes(tmp_path):
    """A note whose files membership exactly matches its same-id machine
    group is restored human_claimed=False (still eligible for future
    processing); a note that was hand-edited to diverge from what the
    machine would produce is restored human_claimed=True. The old claim-all
    rebuild marked both as claimed, freezing the untouched one too.
    """
    root = tmp_path / "store"
    (root / "C" / "R1").mkdir(parents=True)
    (root / "C" / "R2").mkdir(parents=True)
    # Distinct geometry so the two single-file groups get distinct content
    # hashes (and thus distinct group ids — group_id is purely hash-derived).
    trimesh.creation.box(extents=[5, 5, 30]).export(root / "C" / "R1" / "orc.stl")
    trimesh.creation.box(extents=[20, 20, 80]).export(root / "C" / "R2" / "troll.stl")
    cfg = Config(
        store_root=root,
        vault_dir=tmp_path / "vault",
        thumbs_dir=tmp_path / "thumbs",
        footprints_dir=tmp_path / "footprints",
        cache_db=tmp_path / "cache.db",
    )
    ingest(cfg)
    notes = sorted((cfg.vault_dir / "models").glob("*.md"))
    assert len(notes) == 2

    # Hand-edit one note so its files membership can never match a machine
    # group again (fabricated hash the pipeline never produced).
    diverged_note, untouched_note = notes
    post = frontmatter.load(diverged_note)
    post.metadata["files"][0]["hash"] = "deadbeef" * 4
    with open(diverged_note, "w", encoding="utf-8") as f:
        frontmatter.dump(post, f)

    cfg.cache_db.unlink()
    rebuild_cache(cfg)

    diverged_id = frontmatter.load(diverged_note).metadata["id"]
    untouched_id = frontmatter.load(untouched_note).metadata["id"]
    cache = Cache(cfg.cache_db)
    diverged_row = cache.conn.execute(
        "SELECT human_claimed FROM groups WHERE group_id=?", (diverged_id,)
    ).fetchone()
    untouched_row = cache.conn.execute(
        "SELECT human_claimed FROM groups WHERE group_id=?", (untouched_id,)
    ).fetchone()
    cache.close()
    assert diverged_row["human_claimed"] == 1
    assert untouched_row["human_claimed"] == 0


def test_new_file_joins_group_after_rebuild(cfg):
    """Cache loss + rebuild + a new pose file landing in an existing model's
    folder: the file must JOIN the model's group on the next ingest (note
    updated in place), not fragment into its own singleton note. Under the
    old claim-all rebuild, orc.stl's hash would be marked claimed, excluding
    it from the next folder scan entirely — orc_pose2.stl would then be
    grouped alone, creating a stray second note. This test fails against
    that code.
    """
    ingest(cfg)
    cfg.cache_db.unlink()
    rebuild_cache(cfg)

    trimesh.creation.box(extents=[5, 5, 31]).export(cfg.store_root / "C" / "R" / "orc_pose2.stl")
    s = ingest(cfg)

    assert s.created == 0
    assert s.updated == 1
    models = list((cfg.vault_dir / "models").glob("*.md"))
    assert len(models) == 1  # joined the existing note; no fragment singleton note
    note = frontmatter.load(models[0])
    assert {f["path"] for f in note.metadata["files"]} == {
        "C/R/orc.stl",
        "C/R/orc_pose2.stl",
    }


def test_rebuild_skips_malformed_yaml(cfg):
    """One good note + one malformed-YAML note → rebuild returns 1, no raise;
    the good note's membership is correctly restored despite the corrupt
    sibling (checked via group_members, not claimed_hashes — the good note
    matches its machine group exactly, so it's restored unclaimed)."""
    ingest(cfg)
    good_note = next((cfg.vault_dir / "models").glob("*.md"))
    good_meta = frontmatter.load(good_note).metadata
    good_id, good_hash = good_meta["id"], good_meta["files"][0]["hash"]
    cfg.cache_db.unlink()

    # Add a malformed YAML note
    models_dir = cfg.vault_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    malformed_note = models_dir / "malformed.md"
    malformed_note.write_text("---\nid: [unterminated\n---\ncontent")

    n = rebuild_cache(cfg)
    assert n == 1  # Only the good note is counted
    cache = Cache(cfg.cache_db)
    assert cache.group_members(good_id) == {good_hash}
    cache.close()


def test_rebuild_skips_missing_hash_field(cfg):
    """One good note + one note with missing 'hash' in files → returns 1, no
    raise; the good note's membership is correctly restored despite the bad
    sibling."""
    ingest(cfg)
    good_note = next((cfg.vault_dir / "models").glob("*.md"))
    good_meta = frontmatter.load(good_note).metadata
    good_id, good_hash = good_meta["id"], good_meta["files"][0]["hash"]
    cfg.cache_db.unlink()

    # Add a note with files that lack 'hash' field
    models_dir = cfg.vault_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    bad_note = models_dir / "bad_files.md"
    bad_note.write_text("---\nid: bad-id\nfiles:\n  - name: orc.stl\n---\ncontent")

    n = rebuild_cache(cfg)
    assert n == 1  # Only the good note is counted
    cache = Cache(cfg.cache_db)
    assert cache.group_members(good_id) == {good_hash}
    cache.close()


def test_rebuild_closes_db_on_exception(cfg):
    """DB connection closed even on early exception; subsequent Cache can open db."""
    ingest(cfg)
    cfg.cache_db.unlink()

    # Add a malformed YAML note to trigger exception during processing
    models_dir = cfg.vault_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    malformed_note = models_dir / "malformed.md"
    malformed_note.write_text("---\nid: [unterminated\n---\ncontent")

    # rebuild_cache should not raise and should close the db properly
    n = rebuild_cache(cfg)
    assert n == 1

    # Verify subsequent Cache can open and use the db (proves no lock/leak)
    cache = Cache(cfg.cache_db)
    cache.get_files()  # Should not raise
    cache.close()
