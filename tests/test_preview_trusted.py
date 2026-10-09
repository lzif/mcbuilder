"""Tests for the direction-trusted preview tier (PLAN §3).

Unit tests pin the mesh math (the truthfulness contract); render tests
pin determinism and the fallback-warning plumbing. Pixel-perfect
assertions are deliberately avoided — geometry is asserted in
unit-cube-local coordinates, rendering is asserted byte-identical.
"""

import pytest
from PIL import Image

import mcbuilder as mb
from mcbuilder import preview_trusted as pt
from mcbuilder.views import parse_views


# ---------------------------------------------------------------- classify

@pytest.mark.parametrize("block,kind", [
    ("minecraft:oak_stairs[facing=north,half=bottom]", "stairs"),
    ("minecraft:stone_brick_stairs[facing=east,half=top,shape=inner_left]", "stairs"),
    ("minecraft:oak_slab[type=bottom]", "slab"),
    ("minecraft:oak_log[axis=y]", "axis"),
    ("minecraft:stripped_spruce_wood[axis=x]", "axis"),
    ("minecraft:purpur_pillar[axis=z]", "axis"),
    ("minecraft:oak_fence", "post"),
    ("minecraft:cobblestone_wall[east=low,north=tall]", "post"),
    ("minecraft:furnace[facing=north]", "facing"),
    ("minecraft:oak_trapdoor[facing=west,half=top,open=false]", "facing"),
    ("minecraft:oak_sign[rotation=4]", "rotation"),
    ("minecraft:white_banner[rotation=11]", "rotation"),
    # Non-log/pillar axis blocks fall through to the labeled-cube fallback.
    ("minecraft:iron_chain[axis=y]", "fallback"),
    ("minecraft:basalt[axis=y]", "fallback"),
    ("minecraft:stone_bricks", "cube"),
    ("minecraft:lantern[hanging=true,waterlogged=false]", "cube"),
    ("minecraft:sea_lantern", "cube"),
    ("lostqol:waystone", "cube"),
])
def test_classify(block, kind):
    name, props = pt._fast._split_blockstate(block)
    assert pt.classify(name, props) == kind


# ---------------------------------------------------------------- stair mesh math

def test_stair_boxes_north_bottom_straight():
    boxes = pt._stair_boxes("north", "bottom", "straight")
    assert boxes == [
        (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),  # base slab
        (0.0, 0.0, 0.5, 1.0, 1.0, 1.0),  # tall back (south) half
    ]


def test_stair_boxes_east_bottom_straight():
    # Tall part rotates to the back = west (-X) half.
    boxes = pt._stair_boxes("east", "bottom", "straight")
    assert boxes == [
        (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),
        (0.0, 0.0, 0.0, 0.5, 1.0, 1.0),
    ]


def test_stair_boxes_south_bottom_straight():
    boxes = pt._stair_boxes("south", "bottom", "straight")
    assert boxes == [
        (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),
        (0.0, 0.0, 0.0, 1.0, 1.0, 0.5),
    ]


def test_stair_boxes_top_half_mirrors_y():
    boxes = pt._stair_boxes("north", "top", "straight")
    assert boxes == [
        (0.0, 0.5, 0.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.5, 1.0, 1.0, 1.0),
    ]


def test_stair_boxes_inner_outer_shapes():
    inner = pt._stair_boxes("north", "bottom", "inner_left")
    assert (0.0, 0.5, 0.0, 0.5, 1.0, 0.5) in inner
    assert len(inner) == 3
    outer = pt._stair_boxes("north", "bottom", "outer_right")
    assert (0.0, 0.0, 0.5, 0.5, 1.0, 1.0) in outer
    assert len(outer) == 2
    # Unknown shape falls back to straight (never crashes the tier).
    assert pt._stair_boxes("north", "bottom", "sideways") == \
        pt._stair_boxes("north", "bottom", "straight")


def test_stair_mesh_has_wedge_not_cube():
    # The cost-driver assertion: a stair is NOT one cube (2 boxes here).
    polys, label = pt.mesh_for_block(
        "minecraft:oak_stairs[facing=north,half=bottom]")
    assert label is None
    # 2 boxes x 6 quads each.
    assert len(polys) == 12


# ---------------------------------------------------------------- other meshes

def test_slab_mesh_types():
    bottom, _ = pt.mesh_for_block("minecraft:oak_slab[type=bottom]")
    top, _ = pt.mesh_for_block("minecraft:oak_slab[type=top]")
    double, _ = pt.mesh_for_block("minecraft:oak_slab[type=double]")
    # Each mesh is one box = 6 quads; box heights differ.
    assert len(bottom) == len(top) == len(double) == 6
    # Bottom slab's quads never reach y=1; top slab's never touch y=0.
    assert all(py <= 0.5 + 1e-9 for pts, _, _ in bottom for _, py, _ in pts)
    assert all(py >= 0.5 - 1e-9 for pts, _, _ in top for _, py, _ in pts)


def test_axis_mesh_has_band():
    polys, _ = pt.mesh_for_block("minecraft:oak_log[axis=y]")
    # Cube (6) + band box (6).
    assert len(polys) == 12
    # The band pokes slightly outside the unit cube on X/Z.
    xs = [px for pts, _, _ in polys for px, _, _ in pts]
    assert min(xs) < 0.0 and max(xs) > 1.0


def test_facing_mesh_has_plate():
    polys, _ = pt.mesh_for_block("minecraft:furnace[facing=north]")
    # Cube (6) + plate box (6).
    assert len(polys) == 12
    # The plate protrudes past z=0 on the north face.
    zs = [pz for pts, _, _ in polys for _, _, pz in pts]
    assert min(zs) < 0.0


def test_trapdoor_mesh_is_thin():
    polys, _ = pt.mesh_for_block(
        "minecraft:oak_trapdoor[facing=north,half=bottom,open=false]")
    ys = [py for pts, _, _ in polys for _, py, _ in pts]
    # The panel never reaches full height (0.1875 thick + plate).
    assert max(ys) < 0.9


def test_rotation_mesh_has_arrow():
    polys, _ = pt.mesh_for_block("minecraft:oak_sign[rotation=4]")
    # Cube (6) + 1 triangle.
    assert len(polys) == 7
    tri = polys[-1]
    assert len(tri[0]) == 3


def test_rotation_arrow_direction_matches_plan_table():
    # PLAN §3: rotation=0 -> south, 4 -> west, 8 -> north, 12 -> east
    # (CW90 adds +4 and maps south->west). The arrow tip must point there.
    cases = [
        (0, 2, 1),   # south (+Z)
        (4, 0, -1),  # west (-X)
        (8, 2, -1),  # north (-Z)
        (12, 0, 1),  # east (+X)
    ]
    for rot, axis, sign in cases:
        polys, _ = pt.mesh_for_block(f"minecraft:oak_sign[rotation={rot}]")
        tip = polys[-1][0][0]
        assert (tip[axis] - 0.5) * sign > 0.2, (rot, tip)


def test_fallback_mesh_is_labeled_magenta():
    polys, label = pt.mesh_for_block("minecraft:iron_chain[axis=y]")
    assert label == "iron_chain"
    assert len(polys) == 6
    colors = {p[2] for p in polys}
    assert colors == {pt._FALLBACK_COLOR}


def test_cube_mesh_plain():
    polys, label = pt.mesh_for_block("minecraft:stone_bricks")
    assert label is None
    assert len(polys) == 6


# ---------------------------------------------------------------- render

def _two_block_build():
    b = mb.Build(seed=3)
    with b:
        b.set(0, 0, 0, "minecraft:oak_stairs[facing=east,half=bottom]")
        b.set(2, 0, 0, "minecraft:oak_log[axis=y]")
        b.set(4, 0, 0, "minecraft:iron_chain[axis=y]")
    return b


def test_trusted_render_produces_pngs_and_counts_fallback(tmp_path):
    b = _two_block_build()
    out = tmp_path / "t"
    result = pt.render(b.grid, out, parse_views("iso;top"), None)
    assert [p.name for p in result] == ["iso.png", "top.png"]
    assert all(p.stat().st_size > 100 for p in result)
    assert result.info["untrusted_blocks"] == {"minecraft:iron_chain": 1}
    assert result.info["views"] == 2


def test_trusted_render_deterministic(tmp_path):
    b = _two_block_build()
    a = pt.render(b.grid, tmp_path / "a", parse_views("iso"), None)
    c = pt.render(b.grid, tmp_path / "c", parse_views("iso"), None)
    assert (tmp_path / "a" / "iso.png").read_bytes() == \
        (tmp_path / "c" / "iso.png").read_bytes()


def test_trusted_render_empty_grid(tmp_path):
    b = mb.Build(seed=3)
    result = pt.render(b.grid, tmp_path / "e", parse_views("top"), None)
    assert len(result) == 1
    assert result.info["untrusted_blocks"] == {}


def test_build_render_trusted_tier(tmp_path):
    b = _two_block_build()
    paths = b.render(str(tmp_path / "r"), views=["iso"], tier="trusted")
    assert len(paths) == 1 and paths[0].name == "iso.png"
    img = Image.open(paths[0])
    assert img.size[0] > 0


def test_trusted_badge_present():
    # The trusted tier is visually distinguishable from the fast tier:
    # a DIRECTIONS TRUSTED badge in the top-left.
    b = _two_block_build()
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        (p,) = pt.render(b.grid, d, parse_views("iso"), None)
        img = Image.open(p).convert("RGB")
    # Badge rect near (10,10): dark green fill differs from the bg.
    assert img.getpixel((12, 12)) != pt._fast._BG
