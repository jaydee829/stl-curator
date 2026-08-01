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


def test_rebuild_restores_groups_as_claimed(cfg):
    ingest(cfg)
    cfg.cache_db.unlink()  # simulate cache loss
    n = rebuild_cache(cfg)
    assert n == 1
    cache = Cache(cfg.cache_db)
    assert len(cache.claimed_hashes()) == 1
    cache.close()


def test_ingest_after_rebuild_is_noop(cfg):
    ingest(cfg)
    cfg.cache_db.unlink()
    rebuild_cache(cfg)
    s = ingest(cfg)
    assert (s.created, s.updated) == (0, 0)


def test_rebuild_skips_malformed_yaml(cfg):
    """One good note + one malformed-YAML note → rebuild returns 1, no raise."""
    ingest(cfg)
    cfg.cache_db.unlink()

    # Add a malformed YAML note
    models_dir = cfg.vault_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    malformed_note = models_dir / "malformed.md"
    malformed_note.write_text("---\nid: [unterminated\n---\ncontent")

    n = rebuild_cache(cfg)
    assert n == 1  # Only the good note is counted
    cache = Cache(cfg.cache_db)
    assert len(cache.claimed_hashes()) == 1
    cache.close()


def test_rebuild_skips_missing_hash_field(cfg):
    """One good note + one note with missing 'hash' in files → returns 1, no raise."""
    ingest(cfg)
    cfg.cache_db.unlink()

    # Add a note with files that lack 'hash' field
    models_dir = cfg.vault_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    bad_note = models_dir / "bad_files.md"
    bad_note.write_text("---\nid: bad-id\nfiles:\n  - name: orc.stl\n---\ncontent")

    n = rebuild_cache(cfg)
    assert n == 1  # Only the good note is counted
    cache = Cache(cfg.cache_db)
    assert len(cache.claimed_hashes()) == 1
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
