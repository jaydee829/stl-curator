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


def test_assembly_both_models_needs_review():
    """
    Multi-member group where every role is 'model' (two distinct-looking stems
    that fuzzy-merge) should have assembly='needs-review'.

    Cores: goblin_v2 vs goblins_v2, token_set_ratio=94.74 (>=80, so they merge).
    Confidence: 94.74/100 = 0.947 (above threshold, so no coarse-collapse).
    Both roles are 'model', so assembly='needs-review'.
    """
    groups = group_folder(recs("goblin_v2.stl", "goblins_v2.stl"), VOCAB, CFG)
    assert len(groups) == 1
    assert groups[0].assembly == "needs-review"


def test_coarse_collapse_low_confidence():
    """
    When any group's confidence falls below group_confidence_min, the entire
    folder collapses to a single 'needs-review' group, including all other groups.

    Forms TWO clusters under ordinary clustering:
    - Cluster A (singleton): troll_king (confidence 1.0, >= threshold)
    - Cluster B (chain-merge): goblin, goblins, goblins_v2
      - goblin vs goblins: 92.31
      - goblin vs goblins_v2: 75.00 (below 80, but goblins merges with both)
      - goblins vs goblins_v2: 82.35
      - Mean pairwise: (92.31 + 75.00 + 82.35) / 3 = 83.22, conf = 0.832

    With group_confidence_min=0.85: Cluster B (0.832 < 0.85) triggers collapse.
    The gate collapses the ENTIRE FOLDER into ONE group with all 4 files.

    Without the gate: would return 2 separate groups (troll_king + goblin cluster).
    This test discriminates: it MUST fail if the collapse gate is disabled.
    """
    cfg_high_threshold = Config(
        store_root=Path("."),
        vault_dir=Path("."),
        thumbs_dir=Path("."),
        footprints_dir=Path("."),
        cache_db=Path(":memory:"),
        group_confidence_min=0.85,
    )
    groups = group_folder(
        recs("troll_king.stl", "goblin.stl", "goblins.stl", "goblins_v2.stl"),
        VOCAB,
        cfg_high_threshold,
    )
    assert len(groups) == 1
    assert groups[0].assembly == "needs-review"
    assert len(groups[0].members) == 4
    assert groups[0].confidence == pytest.approx(0.832, abs=0.01)


def test_ungrouped_fallback_title():
    """
    When coarse-collapse is triggered with top-level files (no parent folder),
    the title should be "Ungrouped" (fallback for empty parent.name).

    Uses top-level rel_paths like "goblin.stl" (parent="").
    """
    # Create records with top-level rel_paths (no folder prefix)
    top_level_recs = [
        FileRecord("goblin.stl", Path("goblin.stl"), "hash_goblin", 1, 1.0, "stl"),
        FileRecord("goblins.stl", Path("goblins.stl"), "hash_goblins", 1, 1.0, "stl"),
        FileRecord("goblins_v2.stl", Path("goblins_v2.stl"), "hash_goblins_v2", 1, 1.0, "stl"),
    ]
    cfg_high_threshold = Config(
        store_root=Path("."),
        vault_dir=Path("."),
        thumbs_dir=Path("."),
        footprints_dir=Path("."),
        cache_db=Path(":memory:"),
        group_confidence_min=0.85,
    )
    groups = group_folder(top_level_recs, VOCAB, cfg_high_threshold)
    assert len(groups) == 1
    assert groups[0].title == "Ungrouped"
    assert groups[0].assembly == "needs-review"
