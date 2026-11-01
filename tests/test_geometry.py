"""Tests for Geometry and Build.place: define once, stamp many."""

import pytest

import mcbuilder as mb
from mcbuilder import shapes
from mcbuilder.build import Build, BuildError
from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry


def _build():
    b = Build(seed=1)
    b.__enter__()
    return b


# ---------------------------------------------------------------- Geometry


def test_geometry_starts_empty():
    g = Geometry()
    assert len(g) == 0
    assert not g
    assert g.cells() == []
    assert g.bounds() is None


def test_geometry_set_canonicalizes():
    g = Geometry()
    g.set(1, 2, 3, "minecraft:stone_bricks")
    g.set(0, 0, 0, "minecraft:oak_stairs[facing=south,half=bottom]")
    assert g.cells() == [
        (1, 2, 3, "minecraft:stone_bricks"),
        (0, 0, 0, "minecraft:oak_stairs[facing=south,half=bottom]"),
    ]
    assert g.bounds() == ((0, 0, 0), (1, 2, 3))


def test_geometry_set_rejects_bad_coords_and_blocks():
    g = Geometry()
    with pytest.raises(TypeError):
        g.set(1.5, 0, 0, "minecraft:stone")
    with pytest.raises(TypeError):
        g.set(True, 0, 0, "minecraft:stone")
    with pytest.raises(ValueError):
        g.set(0, 0, 0, "not a block!!!")


def test_geometry_add_composites():
    a = shapes.pillar((0, 0, 0), 2, "minecraft:stone")
    b = shapes.pillar((0, 0, 0), 3, "minecraft:oak_planks")
    c = a + b
    assert len(c) == 5
    assert len(a) == 2 and len(b) == 3  # operands untouched
    # Later wins on overlap when stamped (same rule as Build.set).
    d = shapes.box((0, 0, 0), (0, 0, 0), "minecraft:stone")
    e = shapes.box((0, 0, 0), (0, 0, 0), "minecraft:gold_block")
    combo = d + e
    assert combo.cells()[-1][3] == "minecraft:gold_block"


def test_geometry_add_rejects_non_geometry():
    with pytest.raises(TypeError):
        shapes.pillar((0, 0, 0), 1, "minecraft:stone") + "nope"


# ---------------------------------------------------------------- part factories


def test_part_pillar_relative():
    g = shapes.pillar((0, 0, 0), 3, "minecraft:oak_log")
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_log"),
        (0, 1, 0, "minecraft:oak_log"),
        (0, 2, 0, "minecraft:oak_log"),
    ]


def test_part_box_relative_corners_any_order():
    g = shapes.box((1, 0, 1), (0, 0, 0), "minecraft:stone")
    assert len(g) == 4
    assert g.bounds() == ((0, 0, 0), (1, 0, 1))


def test_part_stairs_run_relative_facing():
    g = shapes.stairs((0, 0, 0), "north", "minecraft:oak_stairs", length=2)
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_stairs[facing=north,half=bottom]"),
        (0, 1, -1, "minecraft:oak_stairs[facing=north,half=bottom]"),
    ]


def test_part_stairs_run_width():
    g = shapes.stairs((0, 0, 0), "east", "minecraft:oak_stairs", length=1, width=2)
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_stairs[facing=east,half=bottom]"),
        (0, 0, 1, "minecraft:oak_stairs[facing=east,half=bottom]"),
    ]


def test_part_railing_relative():
    g = shapes.line((0, 0, 0), (2, 0, 0), "minecraft:oak_fence")
    assert [c[:3] for c in g.cells()] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


# ---------------------------------------------------------------- Build.place


def test_place_stamps_at_offset():
    b = _build()
    g = shapes.pillar((0, 0, 0), 2, "minecraft:stone")
    b.place(g, at=(10, 5, -3))
    arr, palette, _ = b.grid.to_dense()
    assert arr.shape == (1, 2, 1)
    assert palette[arr[0, 0, 0]] == "minecraft:stone"
    assert palette[arr[0, 1, 0]] == "minecraft:stone"


def test_place_same_geometry_many_times():
    b = _build()
    g = shapes.pillar((0, 0, 0), 2, "minecraft:stone")
    b.place(g, at=(0, 0, 0))
    b.place(g, at=(5, 0, 0))
    assert b.grid.count_non_air() == 4
    assert len(g) == 2  # geometry never mutated by stamping


def test_place_empty_geometry_is_noop():
    b = _build()
    b.place(Geometry(), at=(0, 0, 0))
    assert b.grid.count_non_air() == 0


def test_place_requires_batch():
    b = Build(seed=1)
    with pytest.raises(BuildError, match="with BUILD"):
        b.place(shapes.pillar((0, 0, 0), 1, "minecraft:stone"), at=(0, 0, 0))


def test_place_validates_args():
    b = _build()
    g = shapes.pillar((0, 0, 0), 1, "minecraft:stone")
    with pytest.raises(BuildError, match="Geometry"):
        b.place("not-a-geometry", at=(0, 0, 0))
    with pytest.raises(BuildError, match="at must be 3 ints"):
        b.place(g, at=(0, 0))
    with pytest.raises(BuildError, match="must be ints"):
        b.place(g, at=(0.5, 0, 0))
    # place() itself is keyword-only for at (anti-context rule: no default).
    with pytest.raises(TypeError):
        b.place(g, (0, 0, 0))


def test_place_overwrite_last_wins():
    b = _build()
    b.place(shapes.box((0, 0, 0), (0, 0, 0), "minecraft:stone"), at=(3, 3, 3))
    b.place(shapes.box((0, 0, 0), (0, 0, 0), "minecraft:gold_block"), at=(3, 3, 3))
    arr, palette, _ = b.grid.to_dense()
    assert palette[arr[0, 0, 0]] == "minecraft:gold_block"
    assert b.grid.overwrite_count == 1


def test_place_provenance_points_at_script_line():
    import inspect

    b = _build()
    g = shapes.pillar((0, 0, 0), 1, "minecraft:stone")
    b.place(g, at=(0, 0, 0))
    expected_line = inspect.currentframe().f_lineno - 1  # the place() call above
    _, _, provenance = b.grid.to_dense()
    (fname, lineno) = provenance[0]
    assert fname == __file__
    # Package frames (Build.place itself) are skipped: the provenance must
    # be the script line that called place(), i.e. the line above.
    assert lineno == expected_line, (lineno, expected_line)


def test_build_render_tier_validation():
    b = _build()
    b.set(0, 0, 0, "minecraft:stone")
    with pytest.raises(BuildError, match="tier"):
        b.render("/tmp/nope", views=["top"], tier="sideways")


# ------------------------------------------------- transforms


def _geo_two_stairs():
    from mcbuilder.geometry import Geometry

    g = Geometry()
    g.set(1, 0, 0, "minecraft:oak_stairs[facing=east,half=bottom]")
    g.set(2, 0, 0, "minecraft:oak_stairs[facing=east,half=bottom]")
    return g


def test_geometry_shift_returns_new():
    g = _geo_two_stairs()
    s = g.shift(10, -1, 5)
    assert (s.cells()[0][:3]) == (11, -1, 5)
    assert g.cells()[0][:3] == (1, 0, 0)  # original untouched


def test_geometry_rotate_positions_and_blockstates():
    g = _geo_two_stairs()
    r = g.rotate("CLOCKWISE_90")
    cells = sorted(r.cells())
    # (1,0,0) -> (0,0,1); (2,0,0) -> (0,0,2); facing east -> south.
    assert cells[0][:3] == (0, 0, 1)
    assert cells[1][:3] == (0, 0, 2)
    assert all(c[3] == "minecraft:oak_stairs[facing=south,half=bottom]" for c in cells), cells
    assert len(g.cells()) == 2  # original untouched


def test_geometry_rotate_about_anchor():
    from mcbuilder.geometry import Geometry

    g = Geometry()
    g.set(1, 0, 0, "minecraft:stone")
    r = g.rotate("CLOCKWISE_90", anchor=(1, 0, 0))
    assert r.cells()[0][:3] == (1, 0, 0)  # anchor cell is fixed
    r2 = g.rotate("CLOCKWISE_180", anchor=(1, 0, 1))
    assert r2.cells()[0][:3] == (1, 0, 2), r2.cells()


def test_geometry_rotate_rejects_bad_rotation():

    with pytest.raises(McbuilderError, match="invalid rotation"):
        _geo_two_stairs().rotate("UPSIDE_DOWN")


def test_geometry_mirror_positions_and_blockstates():
    g = _geo_two_stairs()
    m = g.mirror("x")
    cells = sorted(m.cells())
    assert cells[0][:3] == (-2, 0, 0)
    assert cells[1][:3] == (-1, 0, 0)
    assert all(c[3] == "minecraft:oak_stairs[facing=west,half=bottom]" for c in cells), cells
    with pytest.raises(TypeError, match="axis must be"):
        g.mirror("y")


def test_geometry_carve_removes_box():
    from mcbuilder.geometry import Geometry

    g = Geometry()
    for x in range(3):
        g.set(x, 0, 0, "minecraft:stone")
    c = g.carve((1, 0, 0), (2, 0, 0))
    assert sorted(x for x, _y, _z, _b in c.cells()) == [0]
    assert len(g.cells()) == 3  # original untouched


def test_build_place_rotation_stamps_rotated():

    build = mb.Build(seed=3)
    geo = _geo_two_stairs()
    with build:
        build.place(geo, at=(10, 0, 0), rotation="CLOCKWISE_90")
    assert build.get(10, 0, 1) == "minecraft:oak_stairs[facing=south,half=bottom]"
    assert build.get(10, 0, 2) == "minecraft:oak_stairs[facing=south,half=bottom]"
    assert build.get(11, 0, 0) is None
