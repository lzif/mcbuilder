"""Tests for mcbuilder.rotation: the PLAN §3 normative rotation table.

Mirrors StructurePaster.rotateBlockData() (LostQoL): positions and
blockstates for all four StructureRotations. These semantics are what
the v0.2 acceptance ("pastes correctly at all 4 rotations") rests on.
"""

import pytest

from mcbuilder.errors import McbuilderError
from mcbuilder.rotation import (
    ROTATIONS,
    rotate_blockstate,
    rotate_position,
)


# ---------------------------------------------------------------- positions

def test_rotate_position_none_is_identity():
    for x, z in [(0, 0), (6, 0), (0, 6), (6, 6), (3, 3)]:
        assert rotate_position(x, z, 7, "NONE") == (x, z)


def test_rotate_position_all_rotations_7x7():
    # Corners cycle clockwise: NW -> NE -> SE -> SW -> NW.
    assert rotate_position(0, 0, 7, "CLOCKWISE_90") == (6, 0)
    assert rotate_position(6, 0, 7, "CLOCKWISE_90") == (6, 6)
    assert rotate_position(6, 6, 7, "CLOCKWISE_90") == (0, 6)
    assert rotate_position(0, 6, 7, "CLOCKWISE_90") == (0, 0)
    assert rotate_position(0, 0, 7, "CLOCKWISE_180") == (6, 6)
    assert rotate_position(6, 0, 7, "CLOCKWISE_180") == (0, 6)
    assert rotate_position(0, 0, 7, "COUNTERCLOCKWISE_90") == (0, 6)
    assert rotate_position(6, 0, 7, "COUNTERCLOCKWISE_90") == (0, 0)
    # Center of an odd footprint is fixed by every rotation.
    for r in ROTATIONS:
        assert rotate_position(3, 3, 7, r) == (3, 3)


def test_rotate_position_round_trips():
    for s in (1, 5, 7):
        for x in range(s):
            for z in range(s):
                p = (x, z)
                # CW90 x4 == identity
                q = p
                for _ in range(4):
                    q = rotate_position(*q, s, "CLOCKWISE_90")
                assert q == p
                # CW90 then CCW90 == identity
                q = rotate_position(*p, s, "CLOCKWISE_90")
                assert rotate_position(*q, s, "COUNTERCLOCKWISE_90") == p
                # 180 twice == identity
                q = rotate_position(*p, s, "CLOCKWISE_180")
                assert rotate_position(*q, s, "CLOCKWISE_180") == p


def test_rotate_position_invalid_rotation():
    with pytest.raises(McbuilderError, match="invalid rotation"):
        rotate_position(0, 0, 7, "SPIN")


# ---------------------------------------------------------------- blockstates

@pytest.mark.parametrize("rotation,expected", [
    ("CLOCKWISE_90", {"north": "east", "east": "south", "south": "west", "west": "north"}),
    ("COUNTERCLOCKWISE_90", {"north": "west", "west": "south", "south": "east", "east": "north"}),
    ("CLOCKWISE_180", {"north": "south", "south": "north", "east": "west", "west": "east"}),
])
def test_rotate_facing_all_directions(rotation, expected):
    for src, dst in expected.items():
        got = rotate_blockstate(f"minecraft:oak_stairs[facing={src},half=bottom]", rotation)
        assert got == f"minecraft:oak_stairs[facing={dst},half=bottom]", (src, rotation)


def test_rotate_facing_up_down_invariant():
    for r in ("CLOCKWISE_90", "CLOCKWISE_180", "COUNTERCLOCKWISE_90"):
        assert rotate_blockstate("minecraft:dispenser[facing=up]", r) == \
            "minecraft:dispenser[facing=up]"
        assert rotate_blockstate("minecraft:dispenser[facing=down]", r) == \
            "minecraft:dispenser[facing=down]"


def test_rotate_axis():
    assert rotate_blockstate("minecraft:oak_log[axis=x]", "CLOCKWISE_90") == \
        "minecraft:oak_log[axis=z]"
    assert rotate_blockstate("minecraft:oak_log[axis=z]", "CLOCKWISE_90") == \
        "minecraft:oak_log[axis=x]"
    assert rotate_blockstate("minecraft:oak_log[axis=y]", "CLOCKWISE_90") == \
        "minecraft:oak_log[axis=y]"
    assert rotate_blockstate("minecraft:oak_log[axis=x]", "COUNTERCLOCKWISE_90") == \
        "minecraft:oak_log[axis=z]"
    # 180 does not touch axis.
    assert rotate_blockstate("minecraft:oak_log[axis=x]", "CLOCKWISE_180") == \
        "minecraft:oak_log[axis=x]"


def test_rotate_sign_rotation():
    assert rotate_blockstate("minecraft:oak_sign[rotation=0]", "CLOCKWISE_90") == \
        "minecraft:oak_sign[rotation=4]"
    assert rotate_blockstate("minecraft:oak_sign[rotation=14]", "CLOCKWISE_90") == \
        "minecraft:oak_sign[rotation=2]"
    assert rotate_blockstate("minecraft:oak_sign[rotation=3]", "CLOCKWISE_180") == \
        "minecraft:oak_sign[rotation=11]"
    assert rotate_blockstate("minecraft:oak_sign[rotation=3]", "COUNTERCLOCKWISE_90") == \
        "minecraft:oak_sign[rotation=15]"


def test_rotate_invariants_untouched():
    src = ("minecraft:oak_stairs[facing=north,half=top,shape=inner_left,"
           "waterlogged=true]")
    assert rotate_blockstate(src, "CLOCKWISE_90") == (
        "minecraft:oak_stairs[facing=east,half=top,shape=inner_left,"
        "waterlogged=true]")
    src = "minecraft:oak_trapdoor[facing=west,half=bottom,open=true]"
    assert rotate_blockstate(src, "CLOCKWISE_180") == \
        "minecraft:oak_trapdoor[facing=east,half=bottom,open=true]"


def test_rotate_plain_block_unchanged():
    assert rotate_blockstate("minecraft:stone_bricks", "CLOCKWISE_90") == \
        "minecraft:stone_bricks"
    assert rotate_blockstate("minecraft:stone_bricks", "NONE") == \
        "minecraft:stone_bricks"


def test_rotate_nbt_preserved():
    src = "minecraft:furnace[facing=north]{CustomName:'{\"text\":\"x\"}'}"
    got = rotate_blockstate(src, "CLOCKWISE_90")
    assert got.startswith("minecraft:furnace[facing=east]")
    assert got.endswith("{CustomName:'{\"text\":\"x\"}'}")


def test_rotate_blockstate_round_trip():
    src = "minecraft:oak_stairs[facing=north,half=bottom]"
    q = src
    for _ in range(4):
        q = rotate_blockstate(q, "CLOCKWISE_90")
    assert q == src
    assert rotate_blockstate(
        rotate_blockstate(src, "CLOCKWISE_90"), "COUNTERCLOCKWISE_90") == src


def test_rotate_blockstate_invalid_rotation():
    with pytest.raises(McbuilderError, match="invalid rotation"):
        rotate_blockstate("minecraft:stone", "FLIP")
