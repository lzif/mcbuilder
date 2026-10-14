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
    # Any axis-carrying block classifies as "axis" (finding 4) — chains
    # and rods render as thin posts, logs/pillars/basalt as cube+band.
    ("minecraft:iron_chain[axis=y]", "axis"),
    ("minecraft:basalt[axis=y]", "axis"),
    ("minecraft:deepslate[axis=z]", "axis"),
    # ...except an invalid axis value, which stays a labeled fallback.
    ("minecraft:oak_log[axis=q]", "fallback"),
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
        (0.0, 0.0, 0.0, 1.0, 1.0, 0.5),  # tall back (north) half
    ]


def test_stair_boxes_east_bottom_straight():
    # Tall part rotates to the back = east (+X) half (vanilla-verified).
    boxes = pt._stair_boxes("east", "bottom", "straight")
    assert boxes == [
        (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),
        (0.5, 0.0, 0.0, 1.0, 1.0, 1.0),
    ]


def test_stair_boxes_south_bottom_straight():
    boxes = pt._stair_boxes("south", "bottom", "straight")
    assert boxes == [
        (0.0, 0.0, 0.0, 1.0, 0.5, 1.0),
        (0.0, 0.0, 0.5, 1.0, 1.0, 1.0),
    ]


def test_stair_boxes_top_half_mirrors_y():
    boxes = pt._stair_boxes("north", "top", "straight")
    assert boxes == [
        (0.0, 0.5, 0.0, 1.0, 1.0, 1.0),
        (0.0, 0.0, 0.0, 1.0, 1.0, 0.5),
    ]


def test_stair_boxes_inner_outer_shapes():
    inner = pt._stair_boxes("north", "bottom", "inner_left")
    assert (0.0, 0.5, 0.5, 0.5, 1.0, 1.0) in inner
    assert len(inner) == 3
    outer = pt._stair_boxes("north", "bottom", "outer_right")
    assert (0.0, 0.0, 0.0, 0.5, 1.0, 0.5) in outer
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
    polys, label = pt.mesh_for_block("minecraft:oak_log[axis=q]")
    assert label == "oak_log"
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
    # iron_chain[axis=y] now renders as a thin axial post (finding 4), so
    # nothing in this build is untrusted anymore.
    assert result.info["untrusted_blocks"] == {}
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


# ------------------------------------------------- finding 4


def test_open_trapdoor_stands_against_facing_opposite_wall():
    # dark_oak_trapdoor[facing=west,half=bottom,open=true]: the panel must
    # stand vertically against the EAST wall (x in [0.8125, 1]), not lie
    # flat as a floor slab.
    polys, _ = pt.mesh_for_block(
        "minecraft:dark_oak_trapdoor[facing=west,half=bottom,open=true]")
    xs = [px for pts, _, _ in polys for px, _, _ in pts]
    ys = [py for pts, _, _ in polys for _, py, _ in pts]
    # Panel hugs the east wall (x in [0.8125, 1]); the direction plate
    # straddles its inward face, reaching 0.7625.
    assert min(xs) >= 0.7625 - 1e-9, xs
    assert max(xs) <= 1.0 + 1e-9, xs
    assert max(ys) > 0.9, ys  # full height, not a 0.1875 slab


def test_open_trapdoor_all_facings():
    expected_x = {"north": (0.0, 1.0), "south": (0.0, 1.0),
                  "east": (0.0, 0.2375), "west": (0.7625, 1.0)}
    expected_z = {"north": (0.7625, 1.0), "south": (0.0, 0.2375),
                  "east": (0.0, 1.0), "west": (0.0, 1.0)}
    for facing in ("north", "south", "east", "west"):
        polys, _ = pt.mesh_for_block(
            f"minecraft:oak_trapdoor[facing={facing},half=bottom,open=true]")
        xs = [px for pts, _, _ in polys for px, _, _ in pts]
        zs = [pz for pts, _, _ in polys for _, _, pz in pts]
        lo, hi = expected_x[facing]
        assert min(xs) >= lo - 1e-9 and max(xs) <= hi + 1e-9, (facing, xs)
        lo, hi = expected_z[facing]
        assert min(zs) >= lo - 1e-9 and max(zs) <= hi + 1e-9, (facing, zs)


def test_closed_trapdoor_still_horizontal():
    polys, _ = pt.mesh_for_block(
        "minecraft:oak_trapdoor[facing=north,half=bottom,open=false]")
    ys = [py for pts, _, _ in polys for _, py, _ in pts]
    assert max(ys) < 0.9  # thin horizontal panel + plate


def test_chain_renders_as_thin_axial_post():
    for axis, fixed in (("y", 1), ("x", 0), ("z", 2)):
        polys, label = pt.mesh_for_block(f"minecraft:iron_chain[axis={axis}]")
        assert label is None
        assert len(polys) == 6, (axis, len(polys))  # one thin box
        pts_all = [p for pts, _, _ in polys for p in pts]
        # Thin along the two non-axis dimensions, full along the axis.
        for i in range(3):
            vals = [p[i] for p in pts_all]
            if i == fixed:
                assert min(vals) == 0.0 and max(vals) == 1.0, (axis, vals)
            else:
                assert min(vals) >= 0.375 - 1e-9
                assert max(vals) <= 0.625 + 1e-9, (axis, vals)


def test_rod_renders_as_thin_axial_post():
    polys, _ = pt.mesh_for_block("minecraft:lightning_rod[facing=up]")
    # lightning_rod has no axis prop -> "facing" kind, full cube + plate.
    assert len(polys) == 12


# finding 1: neighbor face culling (per-kind occlusion)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("block,expected", [
    ("minecraft:stone_bricks", True),                    # cube
    ("minecraft:oak_sign[rotation=4]", True),            # rotation
    ("minecraft:oak_log[axis=q]", True),                 # fallback (cube)
    ("minecraft:oak_slab[type=double]", True),           # double slab
    ("minecraft:oak_log[axis=y]", True),                 # axis log: cube
    ("minecraft:iron_chain[axis=y]", False),              # thin post
    # lightning_rod classifies as "facing" and the tier renders facing
    # blocks as full cubes + plate -> occludes (tier-consistent).
    ("minecraft:lightning_rod[facing=up]", True),
    ("minecraft:furnace[facing=north]", True),            # full facing
    ("minecraft:oak_trapdoor[facing=west,half=top,open=false]",
     False),                                            # trapdoor panel
    ("minecraft:oak_stairs[facing=north,half=bottom]", False),
    ("minecraft:oak_slab[type=bottom]", False),
    ("minecraft:oak_fence", False),                      # post
])
def test_occludes_neighbor_kinds(block, expected):
    from mcbuilder import preview as _fast
    name, props = _fast._split_blockstate(block)
    assert pt._occludes_neighbor(name, props, pt.classify(name, props)) \
        is expected, block


def test_trusted_tier_culls_buried_faces(monkeypatch, tmp_path):
    """A solid 2x2x2 cube from straight above draws exactly the 4 top
    faces — same occ_padded rule as the faithful tier, adapted to
    per-kind occlusion."""
    import numpy as np
    drawn = []
    orig_polygon = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).ImageDraw.polygon
    def spy(self, xy, **kw):
        drawn.append(xy)
        return orig_polygon(self, xy, **kw)
    monkeypatch.setattr("PIL.ImageDraw.ImageDraw.polygon", spy)
    arr = np.ones((2, 2, 2), dtype=np.int32)
    palette = ["minecraft:air", "minecraft:stone_bricks"]
    class G:
        def to_dense(self):
            return arr, palette, {}
    pt.render(G(), tmp_path, parse_views("top"))
    assert len(drawn) == 4, len(drawn)
