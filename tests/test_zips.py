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


def test_cleans_partial_extraction_on_error(tmp_path, monkeypatch):
    zip_path = tmp_path / "C" / "kit.zip"
    make_zip(zip_path, ["a.stl"])
    target = zip_path.with_suffix("")

    # Monkeypatch extractall to create target and a partial file, then raise OSError
    original_extractall = zipfile.ZipFile.extractall

    def failing_extractall(self, path=None, members=None, pwd=None):
        path_obj = Path(path) if path else Path(".")
        path_obj.mkdir(parents=True, exist_ok=True)
        (path_obj / "partial.stl").write_text("incomplete")
        raise OSError("Simulated extraction failure")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", failing_extractall)

    # First call should fail, error recorded, target cleaned up
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == []
    assert res.errors and res.errors[0][0] == "C/kit.zip"
    assert not target.exists(), "Partial extraction should be cleaned up"

    # Restore original extractall and call again — should succeed now
    monkeypatch.setattr(zipfile.ZipFile, "extractall", original_extractall)
    res = extract_needed_zips(scan_store(tmp_path), tmp_path)
    assert res.extracted == [target]
    assert (target / "a.stl").exists()
