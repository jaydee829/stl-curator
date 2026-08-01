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


def _strip_long_path_prefix(p: Path) -> Path:
    """Remove Windows long-path prefix if present."""
    s = str(p)
    if s.startswith("\\\\?\\"):
        return Path(s[4:])
    return p


def scan_store(root: Path) -> list[FileRecord]:
    records = []
    scan_root = Path(long_path(root))
    for p in scan_root.rglob("*"):
        if not p.is_file() or p.name.startswith("."):
            continue
        stat = p.stat()
        # Strip prefix from enumerated path before hashing and storing
        abs_path = _strip_long_path_prefix(p)
        records.append(
            FileRecord(
                rel_path=p.relative_to(scan_root).as_posix(),
                abs_path=abs_path,
                hash=hash_file(abs_path),
                size=stat.st_size,
                mtime=stat.st_mtime,
                kind=_KIND_BY_EXT.get(p.suffix.lower(), "other"),
            )
        )
    records.sort(key=lambda r: r.rel_path)
    return records
