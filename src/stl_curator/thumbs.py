from __future__ import annotations

import re
from pathlib import Path

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
