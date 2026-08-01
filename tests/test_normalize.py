import pytest

from stl_curator.grouping import load_vocab, normalize_stem

VOCAB = load_vocab()


@pytest.mark.parametrize(
    "filename,core,role",
    [
        ("goblin_pose1.stl", "goblin", "variant"),
        ("goblin_pose2.stl", "goblin", "variant"),
        ("goblin_helmet.stl", "goblin", "variant"),
        ("goblin_spear_a.stl", "goblin", "variant"),
        ("Goblin Archer.stl", "goblin_archer", "model"),
        ("dragon_body.stl", "dragon", "part"),
        ("dragon_wing_l.stl", "dragon", "part"),
        ("dragon_tail_01.stl", "dragon", "part"),
        ("owlbear_part03.stl", "owlbear", "part"),
        ("troll_32mm_supported.stl", "troll", "model"),
        ("troll-big.final.stl", "troll_big", "model"),
    ],
)
def test_normalize_core_and_role(filename, core, role):
    n = normalize_stem(filename, VOCAB)
    assert (n.core, n.role) == (core, role)


@pytest.mark.parametrize(
    "filename,markers",
    [
        ("troll_32mm_supported.stl", {"32mm", "supported"}),
        ("goblin_presup.stl", {"presup"}),
        ("goblin.stl", set()),
    ],
)
def test_markers_captured(filename, markers):
    assert normalize_stem(filename, VOCAB).markers == markers
