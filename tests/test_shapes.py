"""Tests for mcbuilder.shapes and the matching Build methods."""

import inspect

import pytest

import mcbuilder as mb
from mcbuilder import shapes
from mcbuilder.errors import McbuilderError

STONE = "minecraft:stone"
STAIR = "minecraft:oak_stairs"


def cells(geo):
    return {(x, y, z): b for x, y, z, b in geo.cells()}


# -- Build methods mirror shapes exactly ------------------------------------


@pytest.mark.parametrize("name", shapes.__all__)
def test_every_shape_is_a_build_method_with_the_same_signature(name):
    fn = getattr(shapes, name)
    method = getattr(mb.Build, name)
    assert method.__wrapped__ is fn
    assert inspect.signature(method.__wrapped__) == inspect.signature(fn)


def test_build_method_places_and_returns_geometry():
    b = mb.Build(seed=1)
    with b:
        geo = b.pillar((2, 0, 3), 3, STONE)
    assert geo.bounds() == ((2, 0, 3), (2, 2, 3))
    assert b.count(STONE) == 3


def test_shape_function_places_nothing_until_stamped():
    geo = shapes.pillar((0, 0, 0), 2, STONE)
    b = mb.Build()
    assert b.count(STONE) == 0
    with b:
        placed = b.place(geo, at=(5, 1, 5))
    assert sorted(cells(placed)) == [(5, 1, 5), (5, 2, 5)]


def test_shapes_require_scope_through_build():
    b = mb.Build()
    with pytest.raises(mb.BuildError):
        b.box((0, 0, 0), (1, 1, 1), STONE)


# -- box / walls / pillar / line -------------------------------------------


def test_box_corners_any_order():
    assert len(shapes.box((2, 2, 2), (0, 0, 0), STONE)) == 27


def test_walls_have_no_floor_or_ceiling():
    c = cells(shapes.walls((0, 0, 0), (4, 2, 4), STONE))
    assert (2, 0, 2) not in c and (2, 2, 2) not in c
    assert (0, 1, 2) in c and (4, 1, 2) in c and (2, 1, 0) in c
    assert len(c) == 16 * 3


def test_pillar_validates_height():
    with pytest.raises(McbuilderError):
        shapes.pillar((0, 0, 0), 0, STONE)


def test_line_is_face_connected():
    pts = [(x, y, z) for x, y, z, _ in shapes.line((0, 0, 0), (5, 7, 3), STONE).cells()]
    assert pts[0] == (0, 0, 0) and pts[-1] == (5, 7, 3)
    for a, b in zip(pts, pts[1:]):
        assert sum(abs(a[i] - b[i]) for i in range(3)) == 1


def test_line_axis_aligned_run():
    assert sorted(cells(shapes.line((0, 1, 0), (3, 1, 0), "minecraft:oak_fence"))) == [
        (0, 1, 0),
        (1, 1, 0),
        (2, 1, 0),
        (3, 1, 0),
    ]


# -- stairs -----------------------------------------------------------------


def test_stairs_face_the_climb_direction():
    c = cells(shapes.stairs((0, 0, 0), "north", STAIR, length=3))
    assert c[(0, 2, -2)] == "minecraft:oak_stairs[facing=north,half=bottom]"
    assert len(c) == 3


def test_stairs_target_derives_length():
    c = cells(shapes.stairs((1, 0, 1), "east", STAIR, target=(4, 3, 1)))
    assert max(c)[0] == 4 and (4, 3, 1) in c and len(c) == 4


def test_stairs_unreachable_target():
    with pytest.raises(McbuilderError):
        shapes.stairs((0, 0, 0), "east", STAIR, target=(3, 2, 0))


def test_stairs_needs_exactly_one_of_length_target():
    with pytest.raises(McbuilderError):
        shapes.stairs((0, 0, 0), "east", STAIR)
    with pytest.raises(McbuilderError):
        shapes.stairs((0, 0, 0), "east", STAIR, length=2, target=(1, 1, 0))


def test_stairs_reject_given_facing():
    with pytest.raises(McbuilderError):
        shapes.stairs((0, 0, 0), "east", STAIR + "[facing=west]", length=2)


def test_stairs_width():
    c = cells(shapes.stairs((0, 0, 0), "east", STAIR, length=1, width=3))
    assert sorted(c) == [(0, 0, 0), (0, 0, 1), (0, 0, 2)]


# -- round shapes -----------------------------------------------------------


@pytest.mark.parametrize("axis,step", [("y", (0, 1, 0)), ("x", (1, 0, 0)), ("z", (0, 0, 1))])
def test_cylinder_axis(axis, step):
    c = cells(shapes.cylinder((0, 0, 0), 2, 4, STONE, axis=axis))
    far = tuple(3 * s for s in step)
    assert (0, 0, 0) in c and far in c
    assert tuple(4 * s for s in step) not in c


def test_cylinder_hollow_fill():
    geo = shapes.cylinder(
        (0, 0, 0), 3, 5, "minecraft:glass", axis="x", hollow=True, fill="minecraft:air"
    )
    c = cells(geo)
    assert c[(2, 0, 0)] == "minecraft:air"
    assert c[(2, 3, 0)] == "minecraft:glass"


def test_sphere_dome_and_fill():
    c = cells(shapes.sphere((0, 0, 0), 4, STONE, hollow=True, dome=True, fill="minecraft:air"))
    assert all(y >= 0 for _, y, _ in c)
    assert c[(0, 1, 0)] == "minecraft:air" and c[(0, 4, 0)] == STONE


def test_cone_tapers():
    c = cells(shapes.cone((0, 0, 0), 3, 4, STONE))
    assert (3, 0, 0) in c and (0, 3, 0) in c and (3, 3, 0) not in c


# -- roofs --------------------------------------------------------------------


def test_roof_gable_faces_uphill_with_trim():
    c = cells(
        shapes.roof_gable(
            (0, 5, 0),
            (4, 5, 4),
            STAIR,
            ridge="x",
            verge="minecraft:spruce_stairs",
            eave="minecraft:stone_brick_stairs",
        )
    )
    assert c[(2, 5, 0)] == "minecraft:stone_brick_stairs[facing=south,half=bottom]"
    assert c[(2, 6, 3)] == "minecraft:oak_stairs[facing=north,half=bottom]"
    assert c[(0, 6, 1)].startswith("minecraft:spruce_stairs")
    assert max(y for _, y, _ in c) == 7  # span 5 rises 3 rows


def test_roof_gable_rejects_facing_and_bad_ridge():
    with pytest.raises(McbuilderError):
        shapes.roof_gable((0, 0, 0), (4, 0, 4), STAIR + "[facing=north]", ridge="x")
    with pytest.raises(McbuilderError):
        shapes.roof_gable((0, 0, 0), (4, 0, 4), STAIR, ridge="y")


def test_roof_hip():
    c = cells(shapes.roof_hip((0, 0, 0), (4, 0, 4), STAIR, hip="minecraft:oak_planks"))
    assert c[(0, 0, 0)] == "minecraft:oak_planks"
    assert c[(2, 0, 0)] == "minecraft:oak_stairs[facing=south,half=bottom]"
    assert c[(0, 0, 2)] == "minecraft:oak_stairs[facing=east,half=bottom]"
    assert c[(2, 2, 2)] == "minecraft:oak_planks"


# -- materials ------------------------------------------------------------------


def test_set_accepts_material_spec():
    b = mb.Build(seed=3)
    with b:
        b.set(0, 0, 0, [STONE, "minecraft:andesite"])
        b.set(1, 0, 0, lambda x, y, z: "minecraft:dirt")
    assert b.get(0, 0, 0) in (STONE, "minecraft:andesite")
    assert b.get(1, 0, 0) == "minecraft:dirt"


def test_patches_cluster_and_respect_weights():
    pick = mb.patches([STONE, "minecraft:andesite"], scale=4)
    grid = [[pick(x, 0, z) for x in range(40)] for z in range(40)]
    flat = [b for row in grid for b in row]
    share = flat.count(STONE) / len(flat)
    assert 0.3 < share < 0.7
    same = sum(row[i] == row[i + 1] for row in grid for i in range(39))
    assert same / (40 * 39) > 0.75  # neighbours mostly agree: patches, not speckle
    assert pick(3, 0, 5) == mb.patches([STONE, "minecraft:andesite"], scale=4)(3, 0, 5)
