from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

_PATH_FIELDS = {"store_root", "vault_dir", "thumbs_dir", "footprints_dir", "cache_db"}


@dataclass
class Config:
    store_root: Path
    vault_dir: Path
    thumbs_dir: Path
    footprints_dir: Path
    cache_db: Path
    group_max_simple: int = 6
    group_similarity: int = 80
    group_confidence_min: float = 0.6


def load_config(path: Path | None = None, **overrides) -> Config:
    data: dict = {}
    if path is not None and Path(path).exists():
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    data.update({k: v for k, v in overrides.items() if v is not None})
    kwargs = {}
    for f in fields(Config):
        if f.name in data:
            v = data[f.name]
            kwargs[f.name] = Path(v) if f.name in _PATH_FIELDS else v
    return Config(**kwargs)


def long_path(p: Path) -> str:
    """Windows long-path-safe string for file I/O. Absolute paths get \\\\?\\.

    The \\\\?\\ prefix is a Windows-only escape (it disables MAX_PATH and
    normalization in the Win32 API). On POSIX, paths don't have this limit
    and the literal backslash-prefixed string would corrupt the path, so the
    prefix is only ever added when running on Windows (os.name == "nt").
    """
    if os.name == "nt" and p.is_absolute():
        return "\\\\?\\" + str(p)
    return str(p)
