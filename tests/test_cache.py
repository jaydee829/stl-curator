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


def test_group_claimed_paths(cache):
    cache.upsert_group("g1", ["h1", "h2"], 0.9, human_claimed=True, member_paths=["a.stl", "b.stl"])
    cache.upsert_group("g2", ["h3"], 0.5, member_paths=["c.stl"])
    assert cache.claimed_paths() == {"a.stl", "b.stl"}


def test_claimed_paths_scoped_by_path_not_hash(cache):
    """FINDING NEW-C: two groups can legitimately share a hash (a
    content-identical file cataloged in two different folders) without
    sharing a location. Claiming one group's path must not claim the
    other's path just because they happen to have the same hash — claims
    are location-scoped, not content-scoped."""
    cache.upsert_group("g1", ["h1"], 0.9, human_claimed=True, member_paths=["A/dup.stl"])
    cache.upsert_group("g2", ["h1"], 0.5, member_paths=["B/dup.stl"])
    assert cache.claimed_paths() == {"A/dup.stl"}


def test_duplicates(cache):
    cache.upsert_file(rec(rel="a.stl", h="same"))
    cache.upsert_file(rec(rel="b.stl", h="same"))
    cache.upsert_file(rec(rel="c.stl", h="uniq"))
    assert cache.duplicate_hashes() == {"same": ["a.stl", "b.stl"]}


def test_clear(cache):
    cache.upsert_file(rec())
    cache.clear()
    assert cache.get_files() == []
