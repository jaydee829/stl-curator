from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from stl_curator.scan import FileRecord


@dataclass
class ExtractResult:
    extracted: list[Path] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)


def extract_needed_zips(records: list[FileRecord], root: Path) -> ExtractResult:
    res = ExtractResult()
    for rec in records:
        if rec.kind != "zip":
            continue
        target = rec.abs_path.with_suffix("")
        if target.exists():
            continue
        try:
            with zipfile.ZipFile(rec.abs_path) as z:
                z.extractall(target)
            res.extracted.append(target)
        except (zipfile.BadZipFile, OSError) as e:
            res.errors.append((rec.rel_path, str(e)))
    return res
