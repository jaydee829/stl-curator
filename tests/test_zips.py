import zipfile
from pathlib import Path

from stl_curator.scan import scan_store
from stl_curator.zips import extract_needed_zips


def make_zip(path: Path, names: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for n in names:
            z.writestr(n, b"solid\nendsolid\n")


def test_extracts_new_zip(tmp_path):
    make_zip(tmp_path / "C" / "kit.zip", ["a.stl", "sub/b.stl"])
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == [tmp_path / "C" / "kit"]
    assert (tmp_path / "C" / "kit" / "sub" / "b.stl").exists()
    assert (tmp_path / "C" / "kit.zip").exists()  # original untouched


def test_skips_when_dir_exists(tmp_path):
    make_zip(tmp_path / "C" / "kit.zip", ["a.stl"])
    (tmp_path / "C" / "kit").mkdir(parents=True)
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == []


def test_bad_zip_reported_not_raised(tmp_path):
    bad = tmp_path / "C" / "bad.zip"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"this is not a zip")
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == []
    assert res.errors and res.errors[0][0] == "C/bad.zip"
