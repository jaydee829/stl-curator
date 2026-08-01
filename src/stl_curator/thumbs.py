from __future__ import annotations

import io
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from stl_curator.scan import FileRecord

_GOOD = re.compile(r"render|preview|beauty|box|art|cover|hero", re.IGNORECASE)
_BAD = re.compile(r"support|instruction|assembly|diagram|guide|chitubox|lychee", re.IGNORECASE)


def score_image_candidate(rec: FileRecord) -> float:
    score = float(rec.size)
    name = Path(rec.rel_path).name
    if _GOOD.search(name):
        score *= 3
    if _BAD.search(name):
        score *= 0.1
    return score


def pick_group_image(candidates: list[FileRecord]) -> FileRecord | None:
    if not candidates:
        return None
    return max(candidates, key=score_image_candidate)


def thumb_path(thumbs_dir: Path, group_id: str) -> Path:
    return thumbs_dir / group_id[:2] / f"{group_id}.webp"


def normalize_to_webp(src_image: Path, dest: Path, max_px: int = 512) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src_image) as im:
        im = im.convert("RGB")
        im.thumbnail((max_px, max_px))
        im.save(dest, "WEBP", quality=80)


def _camera_transform(mesh: trimesh.Trimesh) -> np.ndarray:
    center = mesh.bounds.mean(axis=0)
    radius = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])) / 2 or 1.0
    az, el = np.radians(45.0), np.radians(30.0)
    dist = 2.2 * radius
    eye = center + dist * np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
    fwd = center - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    m = np.eye(4)
    m[:3, 0], m[:3, 1], m[:3, 2], m[:3, 3] = right, up, -fwd, eye
    return m


def _render_pyrender(mesh: trimesh.Trimesh, size_px: int) -> np.ndarray:
    import pyrender

    scene = pyrender.Scene(bg_color=[240, 240, 240, 255], ambient_light=[0.3, 0.3, 0.3])
    scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=False))
    cam = pyrender.PerspectiveCamera(yfov=np.radians(45.0))
    pose = _camera_transform(mesh)
    scene.add(cam, pose=pose)
    light = pyrender.DirectionalLight(intensity=3.0)
    scene.add(light, pose=pose)
    r = pyrender.OffscreenRenderer(size_px, size_px)
    try:
        color, _ = r.render(scene)
    finally:
        r.delete()
    return color


def render_thumbnail(stl_path: Path, dest: Path, size_px: int = 512) -> bool:
    try:
        mesh = trimesh.load(str(stl_path), force="mesh")
        if mesh.is_empty or len(mesh.faces) == 0:
            return False
    except Exception:  # noqa: BLE001 — spec: render_thumbnail never raises
        return False
    png_bytes: bytes | None = None
    try:
        color = _render_pyrender(mesh, size_px)
        buf = io.BytesIO()
        Image.fromarray(color).save(buf, "PNG")
        png_bytes = buf.getvalue()
    except Exception:  # noqa: BLE001 — pyrender backend failed, fall back to trimesh
        try:
            scene = trimesh.Scene(mesh)
            scene.camera_transform = _camera_transform(mesh)
            png_bytes = scene.save_image(resolution=(size_px, size_px))
        except Exception:  # noqa: BLE001 — spec: render_thumbnail never raises
            return False
    if not png_bytes:
        return False
    tmp_png = dest.with_suffix(".tmp.png")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_png.write_bytes(png_bytes)
        normalize_to_webp(tmp_png, dest)
    except Exception:  # noqa: BLE001 — spec: render_thumbnail never raises
        return False
    finally:
        tmp_png.unlink(missing_ok=True)
    return True


@lru_cache(maxsize=1)
def render_available() -> bool:
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "probe.stl"
            trimesh.creation.box(extents=[1, 1, 1]).export(p)
            return render_thumbnail(p, Path(td) / "probe.webp", size_px=8)
    except Exception:  # noqa: BLE001 — probe must never raise
        return False
