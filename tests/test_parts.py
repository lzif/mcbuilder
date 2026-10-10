"""Tests for the mcbuilder parts catalog: stairs_run, pillar, railing.

The one-shot parts are sugar over the datablock layer
(``mcbuilder.part.*`` factories + ``Build.place``), so these tests
exercise them against a minimal recording stand-in honoring the
interface the parts depend on: ``build.place(geometry, *, at)``.
"""

import pytest

from mcbuilder.errors import McbuilderError

from mcbuilder import parts


class FakeBuild:
    """Minimal stand-in for mcbuilder.build.Build: records placements."""

    def __init__(self):
        self.placements: dict[tuple[int, int, int], str] = {}

    def place(self, geometry, *, at) -> None:
        ax, ay, az = at
        for dx, dy, dz, block in geometry.cells():
            self.placements[(ax + dx, ay + dy, az + dz)] = block


# ---------------------------------------------------------------- stairs_run

STAIR = "minecraft:oak_stairs"

EXPECTED_FACING = {
    # facing = ascent direction (tall back uphill, climbable) — vanilla
    "north": "north",  # ascending north => facing north
    "south": "south",
    "east": "east",
    "west": "west",
}


@pytest.mark.parametrize("direction,facing", sorted(EXPECTED_FACING.items()))
def test_stairs_run_facing_all_directions(direction, facing):
    """Exact blockstate string placed at every step, for all 4 directions."""
    b = FakeBuild()
    parts.stairs_run(b, (10, 20, 30), direction, 4, STAIR)
    dx, dz = {
        "north": (0, -1),
        "south": (0, 1),
        "east": (1, 0),
        "west": (-1, 0),
    }[direction]
    expected = f"minecraft:oak_stairs[facing={facing},half=bottom]"
    assert len(b.placements) == 4
    for i in range(4):
        pos = (10 + i * dx, 20 + i, 30 + i * dz)
        assert b.placements[pos] == expected, (
            f"step {i} ascending {direction}: expected {expected!r}, "
            f"got {b.placements[pos]!r}"
        )


def test_stairs_run_extra_props_preserved_and_facing_overridden():
    """Extra props survive; the part's facing/half win over pre-set ones."""
    b = FakeBuild()
    parts.stairs_run(
        b, (0, 0, 0), "north", 2, "minecraft:oak_stairs[waterlogged=true,facing=east]"
    )
    assert b.placements[(0, 0, 0)] == (
        "minecraft:oak_stairs[facing=north,half=bottom,waterlogged=true]"
    )
    assert b.placements[(0, 1, -1)] == (
        "minecraft:oak_stairs[facing=north,half=bottom,waterlogged=true]"
    )


def test_stairs_run_nbt_passthrough():
    """NBT on the block string passes through untouched."""
    b = FakeBuild()
    parts.stairs_run(b, (0, 0, 0), "east", 1, 'minecraft:chest{CustomName:"x"}')
    assert b.placements[(0, 0, 0)] == (
        'minecraft:chest[facing=east,half=bottom]{CustomName:"x"}'
    )


@pytest.mark.parametrize(
    "direction,expected_xy_z",
    [
        # width=1 runs move along Z -> widen along +X
        ("north", [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, -1), (1, 1, -1), (2, 1, -1)]),
        # width=1 runs move along X -> widen along +Z
        ("east", [(0, 0, 0), (0, 0, 1), (0, 0, 2), (1, 1, 0), (1, 1, 1), (1, 1, 2)]),
    ],
)
def test_stairs_run_width(direction, expected_xy_z):
    """width>1 extends along the perpendicular axis, from start toward +."""
    b = FakeBuild()
    parts.stairs_run(b, (0, 0, 0), direction, 2, STAIR, width=3)
    assert sorted(b.placements) == sorted(expected_xy_z)


def test_stairs_run_invalid_direction():
    with pytest.raises(McbuilderError, match="invalid direction"):
        parts.stairs_run(FakeBuild(), (0, 0, 0), "up", 3, STAIR)


def test_stairs_run_invalid_length_width():
    with pytest.raises(McbuilderError, match="length"):
        parts.stairs_run(FakeBuild(), (0, 0, 0), "north", 0, STAIR)
    with pytest.raises(McbuilderError, match="width"):
        parts.stairs_run(FakeBuild(), (0, 0, 0), "north", 3, STAIR, width=0)


# ------------------------------------------------------- stairs_run target=


def test_stairs_run_target_places_top_step_exactly():
    """target= is the absolute cell the TOP (highest) step must occupy."""
    b = FakeBuild()
    parts.stairs_run(b, (10, 20, 30), "north", block=STAIR, target=(10, 24, 26))
    # 5 steps ascending north: top step is start + 4 toward north = (10, 24, 26)
    assert len(b.placements) == 5
    expected = "minecraft:oak_stairs[facing=north,half=bottom]"
    assert b.placements[(10, 24, 26)] == expected
    for i in range(5):
        assert b.placements[(10, 20 + i, 30 - i)] == expected


def test_stairs_run_target_matches_manual_length():
    """Derived length from target= equals the explicit length= contract."""
    for direction, target in [
        ("east", (3, 3, 0)),
        ("west", (-4, 4, 5)),
        ("south", (2, 2, 7)),
        ("north", (-1, 6, -6)),
    ]:
        b_len, b_tgt = FakeBuild(), FakeBuild()
        dx, dz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[
            direction
        ]
        rise = target[1]
        start = (target[0] - rise * dx, 0, target[2] - rise * dz)
        parts.stairs_run(b_len, start, direction, rise + 1, STAIR)
        parts.stairs_run(b_tgt, start, direction, block=STAIR, target=target)
        assert b_tgt.placements == b_len.placements


def test_stairs_run_target_same_cell_is_one_step():
    """target == start is a valid 1-step run."""
    b = FakeBuild()
    parts.stairs_run(b, (5, 5, 5), "east", block=STAIR, target=(5, 5, 5))
    assert b.placements == {
        (5, 5, 5): "minecraft:oak_stairs[facing=east,half=bottom]"
    }


def test_stairs_run_target_unreachable():
    b = FakeBuild()
    # rise != horizontal travel (off the 1:1 diagonal)
    with pytest.raises(ValueError, match="not reachable"):
        parts.stairs_run(b, (0, 0, 0), "east", block=STAIR, target=(3, 2, 0))
    # nonzero perpendicular offset
    with pytest.raises(ValueError, match="not reachable"):
        parts.stairs_run(b, (0, 0, 0), "east", block=STAIR, target=(3, 3, 1))
    # target below the start
    with pytest.raises(ValueError, match="not reachable"):
        parts.stairs_run(b, (0, 5, 0), "north", block=STAIR, target=(0, 4, -1))
    # travel away from the direction (negative along)
    with pytest.raises(ValueError, match="not reachable"):
        parts.stairs_run(b, (0, 0, 0), "east", block=STAIR, target=(-2, 2, 0))
    # malformed target
    with pytest.raises(ValueError, match="target"):
        parts.stairs_run(b, (0, 0, 0), "east", block=STAIR, target=(1, 2))


def test_stairs_run_length_and_target_mutually_exclusive():
    b = FakeBuild()
    with pytest.raises(ValueError, match="mutually exclusive"):
        parts.stairs_run(b, (0, 0, 0), "east", 4, STAIR, target=(3, 3, 0))
    with pytest.raises(ValueError, match="one of length or target"):
        parts.stairs_run(b, (0, 0, 0), "east", block=STAIR)


def test_stairs_run_target_build_delegate():
    """BUILD.stairs_run accepts target= the same way."""
    from mcbuilder.build import Build

    b = Build()
    with b:
        geo = b.stairs_run((0, 0, 0), "south", block=STAIR, target=(0, 2, 2))
    assert len(geo.cells()) == 3
    (minx, miny, minz), (maxx, maxy, maxz) = geo.bounds()
    assert (maxx, maxy, maxz) == (0, 2, 2)


# ---------------------------------------------------------------------- pillar

def test_pillar_height_and_verbatim_block():
    """height blocks stacked from base (inclusive), string placed verbatim."""
    b = FakeBuild()
    verbatim = "minecraft:oak_log[axis=y]"
    parts.pillar(b, (3, 5, 7), 4, verbatim)
    assert len(b.placements) == 4
    for i in range(4):
        assert b.placements[(3, 5 + i, 7)] == verbatim


def test_pillar_rejects_nonpositive_height():
    with pytest.raises(McbuilderError, match="height"):
        parts.pillar(FakeBuild(), (0, 0, 0), 0, "minecraft:stone")


# --------------------------------------------------------------------- railing

def test_railing_along_x():
    b = FakeBuild()
    parts.railing(b, (0, 64, 0), (4, 64, 0), "minecraft:oak_fence")
    assert sorted(b.placements) == [(x, 64, 0) for x in range(5)]
    assert all(v == "minecraft:oak_fence" for v in b.placements.values())


def test_railing_along_z_reversed():
    """end < start is fine — the run fills between them inclusive."""
    b = FakeBuild()
    parts.railing(b, (2, 64, 5), (2, 64, 2), "minecraft:oak_fence")
    assert sorted(b.placements) == [(2, 64, z) for z in range(2, 6)]


def test_railing_single_point():
    b = FakeBuild()
    parts.railing(b, (1, 1, 1), (1, 1, 1), "minecraft:oak_fence")
    assert b.placements == {(1, 1, 1): "minecraft:oak_fence"}


def test_railing_y_mismatch_names_problem():
    with pytest.raises(McbuilderError, match="same y level"):
        parts.railing(FakeBuild(), (0, 64, 0), (4, 65, 0), "minecraft:oak_fence")


def test_railing_diagonal_names_problem():
    with pytest.raises(McbuilderError, match="axis-aligned"):
        parts.railing(FakeBuild(), (0, 64, 0), (4, 64, 3), "minecraft:oak_fence")


# ----------------------------------------------------------------- composition

def test_composition_hut_corner():
    """Hut corner: pillar + stairs_run + railing composed in one build."""
    b = FakeBuild()
    # corner post
    parts.pillar(b, (0, 0, 0), 4, "minecraft:oak_log[axis=y]")
    # steps ascending north into the doorway, 2 wide
    parts.stairs_run(b, (0, 0, 5), "north", 3, "minecraft:stone_brick_stairs", width=2)
    # fence railing along the porch edge
    parts.railing(b, (0, 4, -1), (2, 4, -1), "minecraft:oak_fence")

    # pillar: 4 verbatim logs
    for i in range(4):
        assert b.placements[(0, i, 0)] == "minecraft:oak_log[axis=y]"

    # stairs: 3 steps x 2 wide, ascending north (-Z), facing north
    stair = "minecraft:stone_brick_stairs[facing=north,half=bottom]"
    for i in range(3):
        for w in range(2):
            assert b.placements[(w, i, 5 - i)] == stair

    # railing: 3 fence blocks along X at y=4
    for x in range(3):
        assert b.placements[(x, 4, -1)] == "minecraft:oak_fence"

    # nothing else got placed
    assert len(b.placements) == 4 + 6 + 3
