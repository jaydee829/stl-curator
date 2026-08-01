from pathlib import Path

import pytest
from PIL import Image

from stl_curator.scan import FileRecord
from stl_curator.thumbs import (
    normalize_to_webp,
    pick_group_image,
    score_image_candidate,
    thumb_path,
)


def img_rec(name, size=1000):
    return FileRecord(f"C/R/{name}", Path(name), f"h_{name}", size, 1.0, "image")


@pytest.mark.parametrize(
    "better,worse",
    [
        (img_rec("render.png", 1000), img_rec("photo.png", 1000)),
        (img_rec("preview.jpg", 500), img_rec("supports_guide.png", 5000)),
        (img_rec("big.png", 9000), img_rec("small.png", 100)),
        (img_rec("box_art.png", 1000), img_rec("assembly_diagram.png", 1000)),
    ],
)
def test_scoring_prefers(better, worse):
    assert score_image_candidate(better) > score_image_candidate(worse)


def test_pick_none_when_empty():
    assert pick_group_image([]) is None


def test_thumb_path_content_addressed(tmp_path):
    assert thumb_path(tmp_path, "g7f3a2c1") == tmp_path / "g7" / "g7f3a2c1.webp"


def test_normalize_to_webp(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (1024, 768), "red").save(src)
    dest = tmp_path / "out" / "x.webp"
    normalize_to_webp(src, dest)
    with Image.open(dest) as im:
        assert im.format == "WEBP"
        assert max(im.size) <= 512
