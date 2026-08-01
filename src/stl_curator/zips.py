from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from stl_curator.config import long_path
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
        target_existed = False
        try:
            target_existed = target.exists()
            # Use long_path for both opening and extracting to handle Windows MAX_PATH
            with zipfile.ZipFile(long_path(rec.abs_path)) as z:
                z.extractall(long_path(target))
            res.extracted.append(target)
        except (zipfile.BadZipFile, OSError) as e:
            # Clean up partial extraction if this run created the target dir
            if target.exists() and not target_existed:
                shutil.rmtree(target, ignore_errors=True)
            res.errors.append((rec.rel_path, str(e)))
    return res
