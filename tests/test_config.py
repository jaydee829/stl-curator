from pathlib import Path

import pytest

from stl_curator.config import load_config, long_path


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(
        None,
        store_root=tmp_path,
        vault_dir=tmp_path / "v",
        thumbs_dir=tmp_path / "t",
        footprints_dir=tmp_path / "f",
        cache_db=tmp_path / "c.db",
    )
    assert cfg.group_max_simple == 6
    assert cfg.group_similarity == 80
    assert cfg.group_confidence_min == 0.6


def test_file_values_loaded(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'store_root = "X:/store"\nvault_dir = "X:/vault"\n'
        'thumbs_dir = "X:/thumbs"\nfootprints_dir = "X:/fp"\n'
        'cache_db = "X:/cache.db"\ngroup_max_simple = 9\n'
    )
    cfg = load_config(p)
    assert cfg.store_root == Path("X:/store")
    assert cfg.group_max_simple == 9


def test_overrides_beat_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'store_root = "X:/store"\nvault_dir = "X:/vault"\n'
        'thumbs_dir = "X:/thumbs"\nfootprints_dir = "X:/fp"\n'
        'cache_db = "X:/cache.db"\n'
    )
    cfg = load_config(p, store_root=Path("Y:/other"))
    assert cfg.store_root == Path("Y:/other")


@pytest.mark.parametrize(
    "given,expected",
    [
        (Path("C:/x/y.stl"), "\\\\?\\C:\\x\\y.stl"),
        (Path("relative/y.stl"), str(Path("relative/y.stl"))),  # relative paths unwrapped
    ],
)
def test_long_path(given, expected):
    assert long_path(given) == expected
