import pytest

from stl_curator.reports import write_duplicate_report, write_error_report


def test_duplicate_report_lists_paths(tmp_path):
    p = write_duplicate_report({"aabb" * 16: ["a.stl", "b/a.stl"]}, tmp_path)
    text = p.read_text(encoding="utf-8")
    assert p == tmp_path / "reports" / "duplicates.md"
    assert "aabbaabb" in text and "b/a.stl" in text


@pytest.mark.parametrize(
    "writer,fname",
    [
        (write_duplicate_report, "duplicates.md"),
        (write_error_report, "errors.md"),
    ],
)
def test_empty_reports_written(tmp_path, writer, fname):
    p = writer({} if fname == "duplicates.md" else [], tmp_path)
    assert p.name == fname
    assert "None found" in p.read_text(encoding="utf-8")


def test_error_report(tmp_path):
    p = write_error_report([("C/bad.zip", "BadZipFile")], tmp_path)
    assert "C/bad.zip" in p.read_text(encoding="utf-8")
