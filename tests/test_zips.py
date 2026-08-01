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


def test_cleans_partial_extraction_uses_long_path(tmp_path, monkeypatch):
    """Verify cleanup uses long_path via mock capture of rmtree calls."""
    import shutil as shutil_module

    from stl_curator.scan import FileRecord

    # Create a normal zip for testing
    zip_path = tmp_path / "C" / "kit.zip"
    make_zip(zip_path, ["a.stl"])

    # Create a FileRecord for the zip
    rec = FileRecord(
        rel_path="C/kit.zip",
        abs_path=zip_path,
        hash="fakehash",
        size=100,
        mtime=0,
        kind="zip",
    )

    # Monkeypatch extractall to create target and raise OSError
    def failing_extractall(self, path=None, members=None, pwd=None):
        if path:
            path_str = str(path).removeprefix("\\\\?\\")
            path_obj = Path(path_str)
        else:
            path_obj = Path(".")
        path_obj.mkdir(parents=True, exist_ok=True)
        (path_obj / "partial.stl").write_text("incomplete")
        raise OSError("Simulated extraction failure")

    # Capture rmtree calls to verify long_path is used
    rmtree_calls = []
    original_rmtree = shutil_module.rmtree

    def capturing_rmtree(path, ignore_errors=False):
        rmtree_calls.append((str(path), ignore_errors))
        return original_rmtree(path, ignore_errors=ignore_errors)

    monkeypatch.setattr(zipfile.ZipFile, "extractall", failing_extractall)
    monkeypatch.setattr(shutil_module, "rmtree", capturing_rmtree)

    # Call extract_needed_zips with the single record
    res = extract_needed_zips([rec], tmp_path)
    assert res.extracted == []
    assert res.errors and res.errors[0][0] == "C/kit.zip"

    # Verify rmtree was called with the prefixed (long_path) target
    assert len(rmtree_calls) == 1, f"Expected 1 rmtree call, got {len(rmtree_calls)}"
    called_path, called_ignore = rmtree_calls[0]
    # rmtree should be called with long_path(target), which has \\?\ prefix
    assert called_path.startswith("\\\\?\\"), (
        f"rmtree should be called with long_path prefix, got {called_path}"
    )
    assert "kit" in called_path, f"rmtree path should contain target name, got {called_path}"
    assert called_ignore is True, "ignore_errors should be True"
