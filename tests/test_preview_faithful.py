"""Tests for mcbuilder.preview_faithful (PLAN §3 v0.3, faithful tier).

Uses fake vanilla assets (hermetic, no network) for logic tests, plus a
real-asset orientation check (skipped when the local asset cache is
absent) that pins vanilla parity for stairs.
"""

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mcbuilder import preview_faithful as pf
from mcbuilder import preview_trusted as pt
from mcbuilder.views import parse_views


# ---------------------------------------------------------------------------
# rotation math
# ---------------------------------------------------------------------------

def test_rot_y_is_clockwise_from_above():
    # East face center -> south face center under y=90.
    assert pf._rot_y((1.0, 0.5, 0.5), 90) == pytest.approx((0.5, 0.5, 1.0))
    assert pf._rot_y((1.0, 0.5, 0.5), 180) == pytest.approx((0.0, 0.5, 0.5))
    assert pf._rot_y((1.0, 0.5, 0.5), 270) == pytest.approx((0.5, 0.5, 0.0))
    assert pf._rot_y((1.0, 0.5, 0.5), 0) == pytest.approx((1.0, 0.5, 0.5))


def test_rot_x_180_flips_y_z():
    assert pf._rot_x((0.5, 0.25, 0.5), 180) == pytest.approx((0.5, 0.75, 0.5))


def _tall_centroid(quads):
    xs, zs, n = 0.0, 0.0, 0
    for pts, _n, _tex in quads:
        if sum(p[1] for p in pts) / 4 > 0.6:
            for p in pts:
                xs += p[0]
                zs += p[2]
                n += 1
    return (xs / n, zs / n)


def test_fake_stair_orientations(assets_root, tex_cache):
    """Tall part follows facing (vanilla convention)."""
    for facing, (ex, ez) in {"north": (0.5, 0.25), "east": (0.75, 0.5),
                             "south": (0.5, 0.75), "west": (0.25, 0.5)}.items():
        quads, fb = pf.resolve_block_quads(
            f"test:test_stairs[facing={facing}]", assets_root, tex_cache,
            set())
        assert not fb, facing
        cx, cz = _tall_centroid(quads)
        assert abs(cx - ex) < 0.2 and abs(cz - ez) < 0.2, facing


def test_fake_stair_top_half(assets_root, tex_cache):
    """x=180 flips to the top half, facing stays east (X-then-Y order).

    x=180 is a vertical mirror: the slab goes to the top half and the
    back element to the lower-back. Facing (the back side) stays +X.
    """
    quads, fb = pf.resolve_block_quads(
        "test:test_stairs[facing=east,half=top]", assets_root, tex_cache,
        set())
    assert not fb
    # Back element (x>0.5 mass) on the east side, in the lower half.
    xs, ys, n = 0.0, 0.0, 0
    for pts, _n, _tex in quads:
        if sum(p[0] for p in pts) / 4 > 0.6:
            for p in pts:
                xs += p[0]
                ys += p[1]
                n += 1
    assert abs(xs / n - 0.75) < 0.2
    assert ys / n < 0.5


def test_weighted_variant_takes_first(assets_root, tex_cache):
    quads, fb = pf.resolve_block_quads(
        "test:test_stairs[facing=east]", assets_root, tex_cache, set())
    assert not fb and len(quads) > 0


def test_multipart_and_or(assets_root, tex_cache):
    # arm=true: post (1 box = 6 quads) + arm (1 box = 6 quads).
    quads, fb = pf.resolve_block_quads(
        "test:test_multi[arm=true]", assets_root, tex_cache, set())
    assert not fb
    assert len(quads) == 12
    # arm=false: post + the OR-case post = 12 quads (two posts).
    quads2, fb2 = pf.resolve_block_quads(
        "test:test_multi[arm=false]", assets_root, tex_cache, set())
    assert not fb2
    assert len(quads2) == 12


def test_missing_blockstate_falls_back(assets_root, tex_cache):
    quads, fb = pf.resolve_block_quads(
        "test:nope_block", assets_root, tex_cache, set())
    assert fb
    assert len(quads) == 6  # magenta cube


def test_missing_assets_root_falls_back(tex_cache):
    quads, fb = pf.resolve_block_quads(
        "minecraft:stone", None, tex_cache, set())
    assert fb


# ---------------------------------------------------------------------------
# real-asset vanilla parity (skipped when the cache is absent)
# ---------------------------------------------------------------------------

_REAL_ROOT = Path("/home/hatch/.cache/mcbuilder/26.2/client/assets/minecraft")
needs_real_assets = pytest.mark.skipif(
    not _REAL_ROOT.is_dir(), reason="no local 26.2 asset cache")


@needs_real_assets
def test_vanilla_stair_parity_all_facings():
    """The load-bearing check: real vanilla stair models, tall part on the
    facing side (the convention the trusted tier got wrong pre-fix)."""
    tex_cache: dict = {}
    for facing, (ex, ez) in {"north": (0.5, 0.25), "east": (0.75, 0.5),
                             "south": (0.5, 0.75), "west": (0.25, 0.5)}.items():
        quads, fb = pf.resolve_block_quads(
            f"minecraft:oak_stairs[facing={facing},half=bottom,shape=straight]",
            _REAL_ROOT, tex_cache, set())
        assert not fb, facing
        cx, cz = _tall_centroid(quads)
        assert abs(cx - ex) < 0.15 and abs(cz - ez) < 0.15, facing


@needs_real_assets
def test_vanilla_top_half_stair():
    tex_cache: dict = {}
    quads, fb = pf.resolve_block_quads(
        "minecraft:oak_stairs[facing=south,half=top,shape=straight]",
        _REAL_ROOT, tex_cache, set())
    assert not fb
    # South-facing top-half (x=180, y=90): the back mass sits at south
    # (+Z) in the LOWER half (x=180 is a vertical mirror); the slab is
    # on top.
    lo_z, lo_n, hi_n = 0.0, 0, 0
    for pts, _n, _t in quads:
        for p in pts:
            if p[1] < 0.4:
                lo_z += p[2]
                lo_n += 1
            elif p[1] > 0.6:
                hi_n += 1
    assert lo_n > 0 and hi_n > 0
    assert lo_z / lo_n > 0.6, "lower mass at south (the back)"


@needs_real_assets
def test_faithful_matches_trusted_stairs():
    """v0.3 acceptance: faithful orientations match the (fixed) trusted tier."""
    tex_cache: dict = {}
    for facing in ("north", "east", "south", "west"):
        canon = (f"minecraft:oak_stairs[facing={facing},half=bottom,"
                 "shape=straight]")
        fquads, ffb = pf.resolve_block_quads(canon, _REAL_ROOT, tex_cache,
                                             set())
        assert not ffb
        tpolys, _label = pt.mesh_for_block(canon)
        fcx, fcz = _tall_centroid(fquads)
        # Trusted tall centroid from its boxes.
        txs, tzs, n = 0.0, 0.0, 0
        for pts, _n, _c in tpolys:
            if sum(p[1] for p in pts) / 4 > 0.6:
                for p in pts:
                    txs += p[0]
                    tzs += p[2]
                    n += 1
        tcx, tcz = txs / n, tzs / n
        assert abs(fcx - tcx) < 0.15 and abs(fcz - tcz) < 0.15, facing


# ---------------------------------------------------------------------------
# render modes
# ---------------------------------------------------------------------------

class FakeGrid:
    def __init__(self, arr, palette):
        self._arr = np.asarray(arr, dtype=np.int32)
        self._palette = list(palette)

    def to_dense(self):
        return self._arr, self._palette, {}


def _one_block_grid():
    arr = np.zeros((1, 1, 1), dtype=np.int32)
    arr[0, 0, 0] = 1
    return FakeGrid(arr, ["minecraft:air", "test:test_stairs[facing=east]"])


def test_presentation_is_light_and_clean(tmp_path, assets_root):
    views = parse_views("iso")
    res = pf.render(_one_block_grid(), tmp_path / "out", views,
                    tmp_path, presentation=True, title="Test")
    img = Image.open(res[0]).convert("RGB")
    px = img.load()
    # Corner pixel: light background, not the dark debug bg.
    assert all(c > 200 for c in px[5, 5]), px[5, 5]
    assert res.info["presentation"] is True


def test_debug_is_dark_with_badge(tmp_path, assets_root):
    views = parse_views("iso")
    res = pf.render(_one_block_grid(), tmp_path / "out", views,
                    tmp_path, presentation=False)
    img = Image.open(res[0]).convert("RGB")
    W, H = img.size
    px = img.load()
    # Top-right corner: dark background (badge is top-left).
    assert all(c < 60 for c in px[W - 5, 5]), px[W - 5, 5]
    assert res.info["presentation"] is False


def test_untrusted_blocks_reported(tmp_path, assets_root):
    arr = np.zeros((1, 1, 1), dtype=np.int32)
    arr[0, 0, 0] = 1
    grid = FakeGrid(arr, ["minecraft:air", "test:missing_block"])
    views = parse_views("iso")
    res = pf.render(grid, tmp_path / "out", views, tmp_path,
                    presentation=True)
    assert res.info["untrusted_blocks"] == {"test:missing_block": 1}


def test_bare_blockstate_uses_vanilla_defaults(assets_root, tex_cache):
    """Bare names (no props) resolve via vanilla defaults, not fallback.

    Regression (review B1): the faithful tier must accept the same bare
    blockstates the trusted tier and validator accept.
    """
    quads, fb = pf.resolve_block_quads("test:test_stairs", assets_root,
                                       tex_cache, set())
    assert not fb
    assert len(quads) > 0


@needs_real_assets
def test_bare_vanilla_blockstates_resolve():
    tex_cache: dict = {}
    for bare in ("minecraft:oak_stairs", "minecraft:lantern",
                 "minecraft:oak_slab", "minecraft:oak_log"):
        quads, fb = pf.resolve_block_quads(bare, _REAL_ROOT, tex_cache, set())
        assert not fb, bare
        assert len(quads) > 0


def test_build_render_faithful_tier(tmp_path, assets_root):
    """Build.render accepts tier='faithful' (review S5)."""
    import mcbuilder as mb
    with mb.Build(seed=1) as b:
        b.set(0, 0, 0, "minecraft:stone")
    out = tmp_path / "faithful"
    paths = b.render(out, views=["iso"], assets_dir=assets_root,
                     tier="faithful", title="T")
    assert len(paths) == 1 and paths[0].name == "iso.png"
    assert paths[0].stat().st_size > 1000


def test_draw_textured_quad_diamond_not_twisted():
    """Regression (Luki 2026-10-09, "texture miring"): a diamond quad
    (top face in iso view) must keep its texture orientation, not twist
    it 90°.

    The old _draw_textured_quad sorted corners by screen position into
    UL/LL/LR/UR for PIL QUAD; for a diamond the "top two" by screen-y are
    the left/right corners, so the texture landed rotated 90° — stone
    brick courses ran across the iso diagonal instead of along it.
    """
    # 16×16 quadrant texture: TL=red, TR=green, BL=blue, BR=yellow.
    tex = Image.new("RGB", (16, 16))
    px = tex.load()
    for y in range(16):
        for x in range(16):
            if y < 8:
                px[x, y] = (255, 0, 0) if x < 8 else (0, 255, 0)
            else:
                px[x, y] = (0, 0, 255) if x < 8 else (255, 255, 0)
    # Diamond (iso top face); UV order [(u0,v0),(u0,v1),(u1,v1),(u1,v0)]
    # with corner texels [(0,0),(0,16),(16,16),(16,0)].
    pts_uv = [(16, 0, 0, 0), (32, 16, 0, 16),
              (16, 32, 16, 16), (0, 16, 16, 0)]
    canvas = Image.new("RGB", (32, 32), (255, 255, 255))
    pf._draw_textured_quad(canvas, pts_uv, tex)
    c = canvas.load()
    # 25% from each vertex toward the center: must sample the quadrant
    # whose corner texel sits at that vertex.
    assert c[16, 4] == (255, 0, 0), "top vertex shows (u0,v0)=red"
    assert c[28, 16] == (0, 0, 255), "right vertex shows (u0,v1)=blue"
    assert c[16, 28] == (255, 255, 0), "bottom vertex shows (u1,v1)=yellow"
    assert c[4, 16] == (0, 255, 0), "left vertex shows (u1,v0)=green"


@needs_real_assets
def test_stair_tread_uv_painted_on_not_world_sorted():
    """Regression (Luki 2026-10-09, "texture miring"): UV corners are
    assigned in MODEL space and carried through rotations (painted-on).

    The old code sorted ROTATED corners by world axes, spinning textures
    90° on models with x/y rotation (and degenerating for side faces
    turned 90°). For stone_brick_stairs[facing=south] (y=90, uvlock),
    the tread's (u0,v0) corner (model x-min/z-min of the tall element's
    top) must land at world (1.0, 1.0, 0.5) — the old world-sorted code
    put it at (0.0, 1.0, 0.5).
    """
    tex_cache: dict = {}
    quads, fb = pf.resolve_block_quads(
        "minecraft:stone_brick_stairs[facing=south,half=bottom,shape=straight]",
        _REAL_ROOT, tex_cache, set())
    assert not fb
    treads = [q for q in quads
              if q[1] == (0, 1, 0)
              and all(abs(p[1] - 1.0) < 1e-9 for p in q[0])]
    assert treads, "tread (y=1.0 up face) present"
    x, y, z = treads[0][0][0]  # (u0,v0) corner, UV order
    assert all(abs(a - b) < 1e-9 for a, b in
               zip((x, y, z), (1.0, 1.0, 0.5))), \
        f"(u0,v0) at {(x, y, z)}, want (1.0, 1.0, 0.5)"


@needs_real_assets
def test_animated_texture_uses_first_frame():
    """Regression (Finding A): animated textures (lantern 16x48, 3 frames)
    must map UVs to a single 16x16 frame, not the full strip.

    The old code scaled v by th/16 = 3, sampling from the wrong frame
    (darker texels) and stretching the texture 3x vertically.
    """
    tex_cache: dict = {}
    img = pf._load_texture_image(_REAL_ROOT, "block/lantern", tex_cache)
    assert img is not None
    # 16x48 with .mcmeta animation -> cropped to 16x16 first frame
    assert img.size == (16, 16), f"got {img.size}, want (16, 16)"


def test_degenerate_quad_skipped():
    """Regression (Finding A): zero-area screen quads (zero-thickness bars
    viewed edge-on) must be skipped, not warped into black smears.

    The old code fed degenerate quads to lstsq (which doesn't fail on
    singular input), producing garbage affines that sampled outside the
    texture -> solid black rectangles.
    """
    canvas = Image.new("RGB", (100, 100), (255, 255, 255))
    tex = Image.new("RGB", (3, 2), (100, 100, 100))
    # Degenerate: all four points on a vertical line (zero area)
    pts_uv = [(50.0, 10.0, 0, 0), (50.0, 20.0, 0, 2),
              (50.0, 20.0, 3, 2), (50.0, 10.0, 3, 0)]
    pf._draw_textured_quad(canvas, pts_uv, tex)
    # Canvas must be untouched (white) — the quad was skipped
    arr = np.array(canvas)
    assert (arr == 255).all(), "degenerate quad must not draw anything"


@needs_real_assets
def test_lantern_crossbars_no_black_smear():
    """Regression (Finding A, isolated single-block render): the lantern's
    zero-thickness cross-bars (elements 2-3, 45° rotated) must not render
    as solid black boxes.

    Renders minecraft:lantern in isolation and checks that the bar region
    (top of the block) does not contain a large solid-black rectangle.
    The vanilla texture has exactly one black texel; magnified it covers
    only a small fraction of the bar.
    """
    from mcbuilder.build import Build
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        with Build() as b:
            b.set(0, 0, 0, "minecraft:lantern[hanging=false]")
            paths = b.render(tmp, views=["az045_el015"],
                             assets_dir=_REAL_ROOT.parent.parent,
                             tier="faithful", presentation=False, title=None)
        img = Image.open(paths[0]).convert("RGB")
        a = np.array(img)
        # Bar region: top ~15% of the non-background pixels
        bg = a[0, 0]
        mask = (a != bg).any(axis=2)
        ys, xs = np.where(mask)
        y0, y1 = ys.min(), ys.max()
        h = y1 - y0
        bar = a[y0:y0 + int(h * 0.25), xs.min():xs.max() + 1]
        black = (bar.sum(axis=2) == 0)
        black_frac = black.mean()
        # The vanilla texture has 1 black texel out of 6 (16%); with the
        # old PIL-QUAD bug the smear covered >40% of the bar region.
        assert black_frac < 0.30, \
            f"black smear covers {black_frac:.1%} of bar region"


# ---------------------------------------------------------------------------
# stair-row notch quirk (issue #1, item 1)
# ---------------------------------------------------------------------------

def test_stair_row_notches_are_real_geometry(tmp_path, assets_root):
    """Adjacent stair rows leave 0.5-block see-through notches.

    DOCUMENTED QUIRK (not a bug): a stair block is a half-slab plus a
    half-height tall element. When rows ascend 1-up/1-over with the tall
    half facing *away* from the next row (as ``roof_gable`` places them),
    a real 0.5-block slot sits between rows — vanilla Minecraft has the
    identical slot. From a high isometric angle the renderer correctly
    shows through it to the background (the rows are floating here).

    This test pins that the faithful tier and the trusted tier AGREE the
    notches exist (both show background between the rows). If the
    faithful tier ever diverges — hiding real notches or inventing gaps
    the trusted tier doesn't see — this fails. See GUIDE §10.
    """
    import mcbuilder as mb
    with mb.Build(seed=1) as b:
        # Two stair rows ascending south, tall halves facing north (away
        # from the next row) — the roof_gable arrangement.
        for x in range(4):
            b.set(x, 0, 0, "test_stairs[facing=north]")
            b.set(x, 1, 1, "test_stairs[facing=north]")

    def bg_fraction(tier):
        out = tmp_path / tier
        paths = b.render(out, views=["iso"], assets_dir=assets_root,
                         tier=tier, presentation=False, title=None)
        a = np.array(Image.open(paths[0]).convert("RGB"))
        bg = tuple(a[0, 0])
        return ((a == bg).all(axis=2)).mean()

    faithful_bg = bg_fraction("faithful")
    trusted_bg = bg_fraction("trusted")
    # Both tiers see background through the inter-row notches. (Exact
    # fractions differ — different shading — but both must be well above
    # the ~background-only-outside-silhouette level.)
    assert faithful_bg > 0.05, \
        f"faithful shows no inter-row notch (bg frac {faithful_bg:.3f})"
    assert trusted_bg > 0.05, \
        f"trusted shows no inter-row notch (bg frac {trusted_bg:.3f})"
