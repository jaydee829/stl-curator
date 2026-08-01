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
