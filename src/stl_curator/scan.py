from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from stl_curator.config import long_path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_KIND_BY_EXT = {".stl": "stl", ".zip": "zip", **{e: "image" for e in IMAGE_EXTS}}


@dataclass
class FileRecord:
    rel_path: str
    abs_path: Path
    hash: str
    size: int
    mtime: float
    kind: str


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_store(root: Path) -> list[FileRecord]:
    records = []
    for p in root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        stat = p.stat()
        records.append(
            FileRecord(
                rel_path=p.relative_to(root).as_posix(),
                abs_path=p,
                hash=hash_file(p),
                size=stat.st_size,
                mtime=stat.st_mtime,
                kind=_KIND_BY_EXT.get(p.suffix.lower(), "other"),
            )
        )
    records.sort(key=lambda r: r.rel_path)
    return records
