"""Tests for the datablock/instancing layer: Geometry, mb.part factories, Build.place.

Steal #1 from docs/bpy-design-notes.md: define once, stamp many. Steal
#3: all new public API is keyword-only. The anti-bpy.context rule: no
implicit placement state — every place() takes explicit coordinates.
"""

import pytest

import mcbuilder as mb
from mcbuilder import part
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
    a = part.pillar(height=2, block="minecraft:stone")
    b = part.pillar(height=3, block="minecraft:oak_planks")
    c = a + b
    assert len(c) == 5
    assert len(a) == 2 and len(b) == 3  # operands untouched
    # Later wins on overlap when stamped (same rule as Build.set).
    d = part.box(c1=(0, 0, 0), c2=(0, 0, 0), block="minecraft:stone")
    e = part.box(c1=(0, 0, 0), c2=(0, 0, 0), block="minecraft:gold_block")
    combo = d + e
    assert combo.cells()[-1][3] == "minecraft:gold_block"


def test_geometry_add_rejects_non_geometry():
    with pytest.raises(TypeError):
        part.pillar(height=1, block="minecraft:stone") + "nope"


# ---------------------------------------------------------------- part factories

def test_part_pillar_relative():
    g = part.pillar(height=3, block="minecraft:oak_log")
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_log"),
        (0, 1, 0, "minecraft:oak_log"),
        (0, 2, 0, "minecraft:oak_log"),
    ]


def test_part_box_relative_corners_any_order():
    g = part.box(c1=(1, 0, 1), c2=(0, 0, 0), block="minecraft:stone")
    assert len(g) == 4
    assert g.bounds() == ((0, 0, 0), (1, 0, 1))


def test_part_stairs_run_relative_facing():
    g = part.stairs_run(direction="north", length=2, block="minecraft:oak_stairs")
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_stairs[facing=north,half=bottom]"),
        (0, 1, -1, "minecraft:oak_stairs[facing=north,half=bottom]"),
    ]


def test_part_stairs_run_width():
    g = part.stairs_run(direction="east", length=1, block="minecraft:oak_stairs", width=2)
    assert g.cells() == [
        (0, 0, 0, "minecraft:oak_stairs[facing=east,half=bottom]"),
        (0, 0, 1, "minecraft:oak_stairs[facing=east,half=bottom]"),
    ]


def test_part_factories_are_keyword_only():
    with pytest.raises(TypeError):
        part.pillar(3, "minecraft:stone")
    with pytest.raises(TypeError):
        part.box((0, 0, 0), (1, 1, 1), "minecraft:stone")
    with pytest.raises(TypeError):
        part.stairs_run("north", 3, "minecraft:oak_stairs")


def test_part_factories_validate():
    with pytest.raises(McbuilderError, match="invalid direction"):
        part.stairs_run(direction="up", length=2, block="minecraft:oak_stairs")
    with pytest.raises(McbuilderError, match="length"):
        part.stairs_run(direction="north", length=0, block="minecraft:oak_stairs")
    with pytest.raises(McbuilderError, match="height"):
        part.pillar(height=0, block="minecraft:stone")
    with pytest.raises(McbuilderError, match="axis-aligned"):
        part.railing(start=(0, 0, 0), end=(1, 0, 1), block="minecraft:oak_fence")


def test_part_railing_relative():
    g = part.railing(start=(0, 0, 0), end=(2, 0, 0), block="minecraft:oak_fence")
    assert [c[:3] for c in g.cells()] == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]


# ---------------------------------------------------------------- Build.place

def test_place_stamps_at_offset():
    b = _build()
    g = part.pillar(height=2, block="minecraft:stone")
    b.place(g, at=(10, 5, -3))
    arr, palette, _ = b.grid.to_dense()
    assert arr.shape == (1, 2, 1)
    assert palette[arr[0, 0, 0]] == "minecraft:stone"
    assert palette[arr[0, 1, 0]] == "minecraft:stone"


def test_place_same_geometry_many_times():
    b = _build()
    g = part.pillar(height=2, block="minecraft:stone")
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
        b.place(part.pillar(height=1, block="minecraft:stone"), at=(0, 0, 0))


def test_place_validates_args():
    b = _build()
    g = part.pillar(height=1, block="minecraft:stone")
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
    b.place(part.box(c1=(0, 0, 0), c2=(0, 0, 0), block="minecraft:stone"), at=(3, 3, 3))
    b.place(part.box(c1=(0, 0, 0), c2=(0, 0, 0), block="minecraft:gold_block"), at=(3, 3, 3))
    arr, palette, _ = b.grid.to_dense()
    assert palette[arr[0, 0, 0]] == "minecraft:gold_block"
    assert b.grid.overwrite_count == 1


def test_place_provenance_points_at_script_line():
    import inspect

    b = _build()
    g = part.pillar(height=1, block="minecraft:stone")
    b.place(g, at=(0, 0, 0))
    expected_line = inspect.currentframe().f_lineno - 1  # the place() call above
    _, _, provenance = b.grid.to_dense()
    (fname, lineno) = provenance[0]
    assert fname == __file__
    # Package frames (Build.place itself) are skipped: the provenance must
    # be the script line that called place(), i.e. the line above.
    assert lineno == expected_line, (lineno, expected_line)


def test_imperative_parts_match_geometry_stamping():
    """parts.* sugar stamps identically to manual part+place."""
    b1, b2 = _build(), _build()
    mb.parts.pillar(b1, (4, 1, -2), 3, "minecraft:stone")
    b2.place(mb.part.pillar(height=3, block="minecraft:stone"), at=(4, 1, -2))
    a1, p1, _ = b1.grid.to_dense()
    a2, p2, _ = b2.grid.to_dense()
    assert p1 == p2 and (a1 == a2).all()

    b3, b4 = _build(), _build()
    mb.parts.stairs_run(b3, (0, 0, 0), "west", 3, "minecraft:oak_stairs")
    b4.place(mb.part.stairs_run(direction="west", length=3, block="minecraft:oak_stairs"),
             at=(0, 0, 0))
    a3, p3, _ = b3.grid.to_dense()
    a4, p4, _ = b4.grid.to_dense()
    assert p3 == p4 and (a3 == a4).all()

    b5, b6 = _build(), _build()
    mb.parts.railing(b5, (1, 2, 3), (1, 2, 6), "minecraft:oak_fence")
    b6.place(mb.part.railing(start=(1, 2, 3), end=(1, 2, 6), block="minecraft:oak_fence"),
             at=(0, 0, 0))
    a5, p5, _ = b5.grid.to_dense()
    a6, p6, _ = b6.grid.to_dense()
    assert p5 == p6 and (a5 == a6).all()


def test_build_render_tier_validation():
    b = _build()
    b.set(0, 0, 0, "minecraft:stone")
    with pytest.raises(BuildError, match="tier"):
        b.render("/tmp/nope", views=["top"], tier="sideways")
