from pathlib import Path

import pytest
import trimesh

from stl_curator.thumbs import render_available, render_thumbnail

pytestmark = pytest.mark.skipif(
    not render_available(), reason="no offscreen GL backend on this machine"
)


@pytest.fixture
def cone_stl(tmp_path) -> Path:
    p = tmp_path / "cone.stl"
    trimesh.creation.cone(radius=5.0, height=20.0).export(p)
    return p


def test_render_produces_webp(cone_stl, tmp_path):
    dest = tmp_path / "t" / "x.webp"
    assert render_thumbnail(cone_stl, dest) is True
    assert dest.exists() and dest.stat().st_size > 0


def test_render_is_deterministic(cone_stl, tmp_path):
    a, b = tmp_path / "a.webp", tmp_path / "b.webp"
    render_thumbnail(cone_stl, a)
    render_thumbnail(cone_stl, b)
    assert a.read_bytes() == b.read_bytes()


def test_render_failure_returns_false(tmp_path):
    bad = tmp_path / "bad.stl"
    bad.write_bytes(b"junk")
    assert render_thumbnail(bad, tmp_path / "out.webp") is False
