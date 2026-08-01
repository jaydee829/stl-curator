from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import trimesh


@dataclass
class MeshFacts:
    height_mm: float | None
    triangles: int | None
    watertight: bool | None
    error: str | None = None


def extract_mesh_facts(path: Path) -> MeshFacts:
    try:
        mesh = trimesh.load(str(path), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            return MeshFacts(None, None, None, "empty mesh")
        lo, hi = mesh.bounds
        return MeshFacts(float(hi[2] - lo[2]), len(mesh.faces), bool(mesh.is_watertight), None)
    except Exception as e:  # noqa: BLE001 — spec §6: errors never halt ingest
        return MeshFacts(None, None, None, str(e))
