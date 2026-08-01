from pathlib import Path

import pytest

from stl_curator.config import Config
from stl_curator.grouping import group_folder, group_id, load_vocab
from stl_curator.scan import FileRecord

VOCAB = load_vocab()
CFG = Config(
    store_root=Path("."),
    vault_dir=Path("."),
    thumbs_dir=Path("."),
    footprints_dir=Path("."),
    cache_db=Path(":memory:"),
)


def recs(*names):
    return [FileRecord(f"C/R/{n}", Path(n), f"hash_{n}", 1, 1.0, "stl") for n in names]


def by_title(groups):
    return {
        g.title: sorted(m.record.rel_path.rsplit("/", 1)[-1] for m in g.members) for g in groups
    }


def test_goblin_poses_one_group_variants():
    groups = group_folder(
        recs("goblin_pose1.stl", "goblin_pose2.stl", "goblin_helmet.stl"), VOCAB, CFG
    )
    assert len(groups) == 1
    assert groups[0].assembly == "variants"
    assert groups[0].title == "Goblin"


def test_split_dragon_one_group_multipart():
    groups = group_folder(
        recs(
            "dragon_body.stl",
            "dragon_wing_l.stl",
            "dragon_wing_r.stl",
            "dragon_tail_01.stl",
        ),
        VOCAB,
        CFG,
    )
    assert len(groups) == 1
    assert groups[0].assembly == "multipart"


def test_two_distinct_models_two_groups():
    groups = group_folder(
        recs("goblin_pose1.stl", "goblin_pose2.stl", "troll_king.stl"), VOCAB, CFG
    )
    assert by_title(groups) == {
        "Goblin": ["goblin_pose1.stl", "goblin_pose2.stl"],
        "Troll King": ["troll_king.stl"],
    }
    assert {g.title: g.assembly for g in groups} == {
        "Goblin": "variants",
        "Troll King": "single",
    }


def test_mixed_kit():
    groups = group_folder(recs("giant_body.stl", "giant_head.stl", "giant_axe.stl"), VOCAB, CFG)
    assert len(groups) == 1
    assert groups[0].assembly == "mixed"


@pytest.mark.parametrize(
    "hashes_a,hashes_b,equal",
    [
        (["h1", "h2"], ["h2", "h1"], True),  # order-invariant
        (["h1", "h2"], ["h1", "h2", "h3"], False),  # membership change
    ],
)
def test_group_id_stability(hashes_a, hashes_b, equal):
    assert (group_id(hashes_a) == group_id(hashes_b)) is equal


def test_group_id_is_8_hex():
    gid = group_id(["h1"])
    assert len(gid) == 8 and int(gid, 16) >= 0
