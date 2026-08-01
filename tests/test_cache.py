from pathlib import Path

import pytest

from stl_curator.cache import Cache
from stl_curator.scan import FileRecord


def rec(rel="a/b.stl", h="h1", size=3, mtime=1.0, kind="stl"):
    return FileRecord(rel, Path("/x") / rel, h, size, mtime, kind)


@pytest.fixture
def cache():
    return Cache(Path(":memory:"))


@pytest.mark.parametrize(
    "probe,expected",
    [
        (rec(), True),  # same path, same hash
        (rec(h="h2"), False),  # same path, different hash
        (rec(rel="other.stl"), False),  # unknown path
    ],
    ids=["same_path_same_hash", "same_path_diff_hash", "unknown_path"],
)
def test_file_unchanged(cache, probe, expected):
    cache.upsert_file(rec())
    assert cache.file_unchanged(probe) is expected


def test_upsert_same_path_updates(cache):
    cache.upsert_file(rec(h="h1"))
    cache.upsert_file(rec(h="h2"))
    rows = cache.get_files()
    assert len(rows) == 1 and rows[0]["hash"] == "h2"


def test_mesh_facts_roundtrip(cache):
    cache.upsert_file(rec())
    cache.set_mesh_facts("h1", 48.2, 1000, True, None)
    row = cache.get_mesh_facts("h1")
    assert row["height_mm"] == 48.2 and row["watertight"] == 1


def test_group_claimed(cache):
    cache.upsert_group("g1", ["h1", "h2"], 0.9, human_claimed=True)
    cache.upsert_group("g2", ["h3"], 0.5)
    assert cache.claimed_hashes() == {"h1", "h2"}


def test_duplicates(cache):
    cache.upsert_file(rec(rel="a.stl", h="same"))
    cache.upsert_file(rec(rel="b.stl", h="same"))
    cache.upsert_file(rec(rel="c.stl", h="uniq"))
    assert cache.duplicate_hashes() == {"same": ["a.stl", "b.stl"]}


def test_clear(cache):
    cache.upsert_file(rec())
    cache.clear()
    assert cache.get_files() == []
