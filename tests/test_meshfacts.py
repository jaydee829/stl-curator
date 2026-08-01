from pathlib import Path

import pytest
import trimesh

from stl_curator.meshfacts import extract_mesh_facts


@pytest.fixture
def box_stl(tmp_path) -> Path:
    p = tmp_path / "box.stl"
    trimesh.creation.box(extents=[10.0, 20.0, 48.5]).export(p)
    return p


def test_height_is_z_extent(box_stl):
    facts = extract_mesh_facts(box_stl)
    assert facts.error is None
    assert facts.height_mm == pytest.approx(48.5)


def test_box_facts(box_stl):
    facts = extract_mesh_facts(box_stl)
    assert facts.triangles == 12
    assert facts.watertight is True


def test_corrupt_file_returns_error_not_raise(tmp_path):
    p = tmp_path / "bad.stl"
    p.write_bytes(b"not a mesh at all")
    facts = extract_mesh_facts(p)
    assert facts.height_mm is None
    assert facts.error
