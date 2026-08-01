import hashlib

import pytest

from stl_curator.scan import hash_file, scan_store


@pytest.fixture
def store(tmp_path):
    (tmp_path / "GoblinCo" / "2024-03").mkdir(parents=True)
    (tmp_path / "GoblinCo" / "2024-03" / "goblin.stl").write_bytes(b"solid a\nendsolid\n")
    (tmp_path / "GoblinCo" / "2024-03" / "render.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "GoblinCo" / "kit.zip").write_bytes(b"PK fake")
    (tmp_path / "GoblinCo" / ".hidden").write_bytes(b"x")
    (tmp_path / "readme.txt").write_bytes(b"hi")
    return tmp_path


def test_hash_file_is_sha256(tmp_path):
    p = tmp_path / "a.stl"
    p.write_bytes(b"hello")
    assert hash_file(p) == hashlib.sha256(b"hello").hexdigest()


def test_scan_finds_all_visible_files(store):
    recs = scan_store(store)
    assert [r.rel_path for r in recs] == [
        "GoblinCo/2024-03/goblin.stl",
        "GoblinCo/2024-03/render.png",
        "GoblinCo/kit.zip",
        "readme.txt",
    ]


@pytest.mark.parametrize(
    "rel,kind",
    [
        ("GoblinCo/2024-03/goblin.stl", "stl"),
        ("GoblinCo/2024-03/render.png", "image"),
        ("GoblinCo/kit.zip", "zip"),
        ("readme.txt", "other"),
    ],
)
def test_kind_classification(store, rel, kind):
    recs = {r.rel_path: r for r in scan_store(store)}
    assert recs[rel].kind == kind


def test_hidden_files_skipped(store):
    assert not any(".hidden" in r.rel_path for r in scan_store(store))
