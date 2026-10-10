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


# ---------------------------------------------------------------------------
# fluid surface height (gap 3)
# ---------------------------------------------------------------------------

H = pf._FLUID_SURFACE_HEIGHT


def test_fluid_surface_height_is_eight_ninths():
    """Pin the constant itself, not just geometry relative to it."""
    assert pf._FLUID_SURFACE_HEIGHT == pytest.approx(8.0 / 9.0)


def _quads_by_normal(canonical):
    quads, fb = pf.resolve_block_quads(canonical, None, {}, set())
    assert not fb, canonical
    by_normal = {}
    for ordered, n, img in quads:
        by_normal[n] = (ordered, img)
    return by_normal


def test_water_top_face_at_fluid_surface_height():
    by_normal = _quads_by_normal("minecraft:water")
    ordered, _img = by_normal[(0, 1, 0)]
    ys = [c[1] for c in ordered]
    assert all(y == pytest.approx(H) for y in ys), ys
    assert max(ys) < 1.0


def test_water_side_faces_stay_full_height():
    by_normal = _quads_by_normal("minecraft:water")
    for n in ((0, 0, -1), (0, 0, 1), (-1, 0, 0), (1, 0, 0)):
        ordered, _img = by_normal[n]
        ys = [c[1] for c in ordered]
        assert min(ys) == 0.0 and max(ys) == 1.0, (n, ys)
    ordered, _img = by_normal[(0, -1, 0)]
    assert all(c[1] == 0.0 for c in ordered)


def test_lava_top_face_at_fluid_surface_height():
    by_normal = _quads_by_normal("minecraft:lava")
    ordered, _img = by_normal[(0, 1, 0)]
    ys = [c[1] for c in ordered]
    assert all(y == pytest.approx(H) for y in ys), ys
    assert max(ys) < 1.0


def test_chest_top_face_not_lowered():
    # Chest shares the _FLUID_RGBA styling dict but is a wooden box,
    # not a fluid — its top must stay at exactly 1.0.
    by_normal = _quads_by_normal("minecraft:chest")
    ordered, _img = by_normal[(0, 1, 0)]
    assert all(c[1] == 1.0 for c in ordered)


def test_flowing_water_uses_same_surface_height():
    # Still-only scope: the fluid path ignores level, so flowing water
    # also renders at 8/9 (documents the accepted approximation).
    by_normal = _quads_by_normal("minecraft:water[level=1]")
    ordered, _img = by_normal[(0, 1, 0)]
    assert all(c[1] == pytest.approx(H) for c in ordered)


def test_fluid_top_alpha_preserved():
    water = _quads_by_normal("minecraft:water")[(0, 1, 0)][1]
    lava = _quads_by_normal("minecraft:lava")[(0, 1, 0)][1]
    for img, want in ((water, 150), (lava, 210)):
        assert img.mode == "RGBA", img.mode
        assert img.getpixel((8, 8))[3] == want


def test_water_render_smoke(tmp_path, assets_root):
    """One water block renders to PNG without exception."""
    import mcbuilder as mb
    with mb.Build(seed=1) as b:
        b.set(0, 0, 0, "minecraft:stone")
        b.set(0, 1, 0, "minecraft:water")
    out = tmp_path / "fluid"
    paths = b.render(out, views=["iso"], assets_dir=assets_root,
                     tier="faithful", title="T")
    assert len(paths) == 1 and paths[0].name == "iso.png"
    assert paths[0].stat().st_size > 1000


def test_fluid_quads_deterministic():
    first, _ = pf.resolve_block_quads("minecraft:water", None, {}, set())
    second, _ = pf.resolve_block_quads("minecraft:water", None, {}, set())
    assert len(first) == len(second) == 6
    for (o1, n1, _i1), (o2, n2, _i2) in zip(first, second):
        assert n1 == n2
        assert o1 == o2


# block-entity approximations (gap4): chest / banner families + sign defaults
# ---------------------------------------------------------------------------

def _mean_rgb(tex):
    d = list(tex.getdata())
    n = len(d)
    return tuple(sum(p[i] for p in d) // n for i in range(3))


def _latch_quads(quads):
    """Latch box quads: narrow horizontal footprint, y in 9/16..13/16
    (straddles the lid/body seam like vanilla's knob)."""
    out = []
    for q in quads:
        pts = q[0]
        if not all(9 / 16 - 1e-6 <= p[1] <= 13 / 16 + 1e-6 for p in pts):
            continue
        if max(p[0] for p in pts) - min(p[0] for p in pts) > 3 / 16 + 1e-6:
            continue
        if max(p[2] for p in pts) - min(p[2] for p in pts) > 3 / 16 + 1e-6:
            continue
        out.append(q)
    return out


def _centroid(quads):
    xs = sum(p[0] for q in quads for p in q[0])
    ys = sum(p[1] for q in quads for p in q[0])
    zs = sum(p[2] for q in quads for p in q[0])
    n = sum(len(q[0]) for q in quads)
    return (xs / n, ys / n, zs / n)


@needs_real_assets
def test_chest_not_fallback():
    """Chest renders as 18 textured quads (body 6 + lid 6 + latch 6)."""
    tex_cache: dict = {}
    for canonical in ("minecraft:chest", "minecraft:chest[facing=east]"):
        quads, fb = pf.resolve_block_quads(canonical, _REAL_ROOT, tex_cache,
                                           set())
        assert not fb, canonical
        assert len(quads) >= 15, (canonical, len(quads))
        # Textured entity quads — never the flat 16×16 fallback cube.
        assert all(q[2].size != (16, 16) for q in quads), canonical
        assert all(q[2].mode in ("RGB", "RGBA") for q in quads), canonical


@needs_real_assets
def test_chest_lid_above_body():
    tex_cache: dict = {}
    quads, fb = pf.resolve_block_quads("minecraft:chest", _REAL_ROOT,
                                       tex_cache, set())
    assert not fb
    # The latch straddles the seam (vanilla knob placement) — exclude it
    # from the body/lid split and pin its span instead.
    latch_ids = {id(q) for q in _latch_quads(quads)}
    assert latch_ids, "no latch quads found"
    rest = [q for q in quads if id(q) not in latch_ids]
    assert min(p[1] for q in quads if id(q) in latch_ids
               for p in q[0]) == pytest.approx(9 / 16)
    assert max(p[1] for q in quads if id(q) in latch_ids
               for p in q[0]) == pytest.approx(13 / 16)
    body = [q for q in rest if _centroid([q])[1] < 0.6]
    lid = [q for q in rest if _centroid([q])[1] >= 0.6]
    assert body and lid
    assert all(p[1] <= 0.63 for q in body for p in q[0])
    assert all(p[1] >= 0.62 for q in lid for p in q[0])
    body_max_y = max(p[1] for q in body for p in q[0])
    lid_min_y = min(p[1] for q in lid for p in q[0])
    assert body_max_y == pytest.approx(10 / 16, abs=0.01)
    assert lid_min_y == pytest.approx(10 / 16, abs=0.01)


@needs_real_assets
def test_chest_facing_rotates_latch():
    """Direction-trust: the latch sits on the facing side, every facing."""
    tex_cache: dict = {}
    for facing, check in (("north", lambda x, z: z < 0.25),
                          ("east", lambda x, z: x > 0.75),
                          ("south", lambda x, z: z > 0.75),
                          ("west", lambda x, z: x < 0.25)):
        quads, fb = pf.resolve_block_quads(
            f"minecraft:chest[facing={facing}]", _REAL_ROOT, tex_cache, set())
        assert not fb, facing
        latch = _latch_quads(quads)
        assert len(latch) == 6, (facing, len(latch))
        cx, _, cz = _centroid(latch)
        assert check(cx, cz), (facing, cx, cz)


@needs_real_assets
def test_chest_textures_per_variant():
    """Each chest variant resolves to its own entity texture."""
    tex_cache: dict = {}
    means = {}
    for name in ("minecraft:chest", "minecraft:trapped_chest",
                 "minecraft:ender_chest", "minecraft:copper_chest",
                 "minecraft:exposed_copper_chest",
                 "minecraft:weathered_copper_chest",
                 "minecraft:oxidized_copper_chest",
                 "minecraft:waxed_copper_chest"):
        quads, fb = pf.resolve_block_quads(name, _REAL_ROOT, tex_cache,
                                           set())
        assert not fb, name
        assert len(quads) >= 15, (name, len(quads))
        # Overall mean color across the textured quads.
        rs = gs = bs = n = 0
        for _, _, tex in quads:
            for p in tex.getdata():
                rs += p[0]
                gs += p[1]
                bs += p[2]
                n += 1
        means[name] = (rs // n, gs // n, bs // n)
    # The variants resolve to genuinely different textures (normal vs
    # trapped differ in only 28/4096 texels — a subtle vanilla reddening
    # — so the hue check uses ender/copper, which are visibly distinct).
    for other in ("minecraft:ender_chest", "minecraft:copper_chest"):
        dist = sum(abs(a - b) for a, b in
                   zip(means["minecraft:chest"], means[other]))
        assert dist > 15, (other, means)


def test_chest_missing_entity_texture_falls_back(assets_root, tex_cache):
    """No textures/entity/ in the cache → graceful degradation.

    chest → the wooden box (intentional, no fallback warning);
    trapped_chest → magenta fallback cube.
    """
    quads, fb = pf.resolve_block_quads("minecraft:chest", assets_root,
                                       tex_cache, set())
    assert not fb
    assert len(quads) == 6
    assert all(q[2].size == (16, 16) for q in quads)
    assert _mean_rgb(quads[0][2]) == (181, 140, 82)

    quads, fb = pf.resolve_block_quads("minecraft:trapped_chest",
                                       assets_root, tex_cache, set())
    assert fb
    assert len(quads) == 6
    assert _mean_rgb(quads[0][2]) == (205, 70, 205)


def test_chest_missing_entity_texture_assets_root_none(tex_cache):
    """assets_root=None skips the entity hook (guard) — same fallbacks."""
    quads, fb = pf.resolve_block_quads("minecraft:chest", None, tex_cache,
                                       set())
    assert not fb
    assert len(quads) == 6
    assert _mean_rgb(quads[0][2]) == (181, 140, 82)

    quads, fb = pf.resolve_block_quads("minecraft:trapped_chest", None,
                                       tex_cache, set())
    assert fb
    assert len(quads) == 6


@needs_real_assets
def test_banner_not_fallback():
    tex_cache: dict = {}
    quads, fb = pf.resolve_block_quads("minecraft:red_banner", _REAL_ROOT,
                                       tex_cache, set())
    assert not fb
    assert len(quads) >= 10, len(quads)
    assert all(q[2].size != (16, 16) for q in quads)

    quads, fb = pf.resolve_block_quads(
        "minecraft:white_wall_banner[facing=east]", _REAL_ROOT, tex_cache,
        set())
    assert not fb
    assert len(quads) >= 10, len(quads)


@needs_real_assets
def test_banner_cloth_tint():
    """Cloth is tinted by the banner's dye color (white base multiplies)."""
    tex_cache: dict = {}

    def cloth_front_mean(canonical):
        quads, fb = pf.resolve_block_quads(canonical, _REAL_ROOT, tex_cache,
                                           set())
        assert not fb
        fronts = [q for q in quads if q[2].size == (22, 41)]
        assert len(fronts) == 1, (canonical, len(fronts))
        assert tuple(fronts[0][1]) == (0.0, 0.0, 1.0), fronts[0][1]
        return _mean_rgb(fronts[0][2])

    r, g, b = cloth_front_mean("minecraft:red_banner[rotation=0]")
    assert r > 100 and r > g + 30 and r > b + 30, (r, g, b)

    r, g, b = cloth_front_mean("minecraft:white_banner[rotation=0]")
    assert r > 150 and g > 150 and b > 150, (r, g, b)
    assert max(r, g, b) - min(r, g, b) < 30, (r, g, b)


@needs_real_assets
def test_banner_standing_rotation():
    """Direction-trust: rotation spins the cloth (22.5° steps)."""
    tex_cache: dict = {}
    for rotation, expected in ((0, (0.0, 0.0, 1.0)),
                               (4, (-1.0, 0.0, 0.0)),
                               (8, (0.0, 0.0, -1.0))):
        quads, fb = pf.resolve_block_quads(
            f"minecraft:red_banner[rotation={rotation}]", _REAL_ROOT,
            tex_cache, set())
        assert not fb, rotation
        fronts = [q for q in quads if q[2].size == (22, 41)]
        assert len(fronts) == 1, (rotation, len(fronts))
        n = tuple(fronts[0][1])
        assert n == pytest.approx(expected, abs=1e-6), (rotation, n)
        # Corner centroids: the cloth front sits on the facing side.
        cx, _, cz = _centroid(fronts)
        if rotation == 0:
            assert cz > 0.5, (rotation, cz)
        elif rotation == 4:
            assert cx < 0.5, (rotation, cx)
        elif rotation == 8:
            assert cz < 0.5, (rotation, cz)


@needs_real_assets
def test_wall_banner_facing():
    """Direction-trust: cloth hangs on the wall opposite the facing."""
    tex_cache: dict = {}
    for facing, normal, wall_check in (
            ("south", (0.0, 0.0, 1.0), lambda x, z: z < 0.25),
            ("west", (-1.0, 0.0, 0.0), lambda x, z: x > 0.75),
            ("north", (0.0, 0.0, -1.0), lambda x, z: z > 0.75),
            ("east", (1.0, 0.0, 0.0), lambda x, z: x < 0.25)):
        quads, fb = pf.resolve_block_quads(
            f"minecraft:white_wall_banner[facing={facing}]", _REAL_ROOT,
            tex_cache, set())
        assert not fb, facing
        cloth = [q for q in quads
                 if q[2].size in ((22, 41), (20, 41), (2, 41), (22, 2))]
        assert len(cloth) == 6, (facing, len(cloth))
        cx, _, cz = _centroid(cloth)
        assert wall_check(cx, cz), (facing, cx, cz)
        fronts = [q for q in cloth if q[2].size == (22, 41)]
        assert len(fronts) == 1, (facing, len(fronts))
        assert tuple(fronts[0][1]) == pytest.approx(normal, abs=1e-6), \
            (facing, fronts[0][1])


@needs_real_assets
def test_sign_bare_resolves():
    """Bare signs resolve via the new _DEFAULT_PROPS (rotation/attached)."""
    tex_cache: dict = {}
    for canonical, min_quads in (("minecraft:oak_sign", 6),
                                 ("minecraft:oak_hanging_sign", 6)):
        quads, fb = pf.resolve_block_quads(canonical, _REAL_ROOT, tex_cache,
                                           set())
        assert not fb, canonical
        assert len(quads) >= min_quads, (canonical, len(quads))


@needs_real_assets
def test_sign_board_faces_facing():
    """oak_wall_sign[facing=east]: the board's front face points +X."""
    tex_cache: dict = {}
    quads, fb = pf.resolve_block_quads(
        "minecraft:oak_wall_sign[facing=east]", _REAL_ROOT, tex_cache, set())
    assert not fb
    boards = [q for q in quads if q[2].size == (24, 12)]
    assert len(boards) == 2, len(boards)  # front + back
    front = next(q for q in boards if tuple(q[1]) == (1.0, 0.0, 0.0))
    back = next(q for q in boards if tuple(q[1]) == (-1.0, 0.0, 0.0))
    assert _centroid([front])[0] > _centroid([back])[0]
    # Real sign texture, not the magenta fallback.
    assert _mean_rgb(front[2]) != (205, 70, 205)


def test_rot_y_degrees_matches_rot_y():
    """_rot_y_degrees ≡ _rot_y applied d/90 times at 90° multiples."""
    pts = [(0.0, 0.0, 0.0), (1.0, 0.5, 0.5), (0.3, 0.7, 0.9),
           (0.5, 0.5, 0.0), (0.25, 1.0, 0.75)]
    for d in (0, 90, 180, 270):
        for p in pts:
            q = p
            for _ in range(d // 90):
                q = pf._rot_y(q, 90)
            r = pf._rot_y_degrees(p, d)
            assert r == pytest.approx(q, abs=1e-9), (d, p, q, r)
    # 45°: halfway between 0° and 90° (sanity on the continuous path).
    r = pf._rot_y_degrees((1.0, 0.5, 0.5), 45)
    assert r == pytest.approx((0.5 + 0.5 * 2 ** 0.5 / 2, 0.5,
                               0.5 + 0.5 * 2 ** 0.5 / 2), abs=1e-9)


# gap 2: smooth lighting / ambient occlusion
# ---------------------------------------------------------------------------

def test_ao_open_face_uniform():
    """An isolated cube's faces get uniform AO (all level 3): the draw
    path must take the fast path, byte-identical to ao=None.

    Part 1 (sampler): every corner vertex of every face of an isolated
    cell samples level 3. Part 2 (draw): _draw_textured_quad with
    ao=None vs ao=(1,1,1,1) produces an identical canvas.
    """
    occ = np.zeros((5, 5, 5), dtype=bool)  # all air
    occ[2, 2, 2] = True  # the cell itself (never sampled, but realistic)
    for normal in [(0, 1, 0), (0, -1, 0), (0, 0, -1),
                   (0, 0, 1), (1, 0, 0), (-1, 0, 0)]:
        ax = 0 if normal[0] else (1 if normal[1] else 2)
        t1, t2 = [t for t in (0, 1, 2) if t != ax]
        for u in (0.0, 1.0):
            for v in (0.0, 1.0):
                vl = [0.0, 0.0, 0.0]
                vl[t1], vl[t2] = u, v
                assert pf._vertex_ao_level(vl, normal, (1, 1, 1), occ) == 3, \
                    f"open-face vertex {vl} normal {normal} must be level 3"
    # draw-level: ao=None vs all-1.0 identical canvas
    tex = Image.new("RGB", (16, 16), (90, 140, 200))
    pts_uv = [(16, 0, 0, 0), (32, 16, 0, 16),
              (16, 32, 16, 16), (0, 16, 16, 0)]
    c1 = Image.new("RGB", (32, 32), (255, 255, 255))
    c2 = Image.new("RGB", (32, 32), (255, 255, 255))
    pf._draw_textured_quad(c1, pts_uv, tex)
    pf._draw_textured_quad(c2, pts_uv, tex, ao=(1.0, 1.0, 1.0, 1.0))
    assert np.array(c1).tolist() == np.array(c2).tolist()


def test_ao_inner_corner_darkens(tmp_path, assets_root):
    """Floor + wall inside corner: the floor's top face must be darker at
    the inner corner than at the open edge (same face).

    Scene: floor cell (0,0,0), occluders at (1,1,0) and (0,1,1). The
    floor top-face vertex at local (1,.,1) sees both sides occluded
    (level 0 -> x0.4); the vertex at (0,.,0) sees open air (level 3).
    Rendered top-down with the uniform-gray test_cube texture, the
    darkest decile of the face pixels (inner corner) must be strictly
    darker than the brightest decile (open edge).

    NOTE: assets_dir must be tmp_path (the fixture's parent):
    _resolve_assets_root looks for <base>/client/assets/minecraft, so
    passing the fixture value itself resolves to None and every block
    renders as the magenta fallback cube.
    """
    import mcbuilder as mb
    with mb.Build(seed=1) as b:
        b.set(0, 0, 0, "test:test_cube")
        b.set(1, 1, 0, "test:test_cube")
        b.set(0, 1, 1, "test:test_cube")
        out = tmp_path / "corner"
        paths = b.render(out, views=["top"], assets_dir=tmp_path,
                         tier="faithful", presentation=True, title=None)
    a = np.array(Image.open(paths[0]).convert("RGB")).astype(np.int32)
    # The test texture is uniform gray (128,128,128); top faces are
    # shade 1.0, and the AO multiply is per-channel identical, so block
    # pixels stay gray (r==g==b, ±1 for the LANCZOS downscale).
    # Background (244,241,235) and the soft shadow fringe are not gray.
    gray = (np.abs(a[..., 0] - a[..., 1]) <= 1) & \
           (np.abs(a[..., 1] - a[..., 2]) <= 1)
    not_bg = np.abs(a[..., 0] - 244) > 8
    mask = gray & not_bg
    # Erode a few px to drop LANCZOS edge blends at the silhouette.
    from PIL import ImageFilter
    m = Image.fromarray(mask.astype(np.uint8) * 255)
    interior = np.array(m.filter(ImageFilter.MinFilter(7))) > 0
    vals = a[interior][..., 0]  # r == g == b here
    assert len(vals) > 100, "expected a sizable uniform-gray face region"
    lo = np.percentile(vals, 10)
    hi = np.percentile(vals, 90)
    inner = vals[vals <= lo].mean()
    outer = vals[vals >= hi].mean()
    assert inner < outer, \
        f"inner corner {inner:.1f} not darker than open edge {outer:.1f}"
    # The darkening is real AO, not noise: open edge ~full brightness.
    assert outer > 120, \
        f"open edge should stay near full brightness, got {outer:.1f}"
    assert inner < 100, \
        f"inner corner should be AO-darkened, got {inner:.1f}"


def test_ao_level_sampler_unit():
    """Unit test of the vanilla AO rule via _vertex_ao_level.

    Padded grid (5,5,5); the sampled cell is array (1,1,1), face normal
    +Y, vertex at local (0,.,0): side1 = array (0,2,1), side2 = array
    (1,2,0), corner = array (0,2,0) — all in the face-adjacent layer.
    """
    def grid(*occluded):
        occ = np.zeros((5, 5, 5), dtype=bool)
        for (x, y, z) in occluded:
            occ[x + 1, y + 1, z + 1] = True
        return occ

    n = (0, 1, 0)
    v = (0.0, 1.0, 0.0)
    assert pf._vertex_ao_level(v, n, (1, 1, 1), grid()) == 3
    assert pf._vertex_ao_level(v, n, (1, 1, 1), grid((0, 2, 1))) == 2
    assert pf._vertex_ao_level(
        v, n, (1, 1, 1), grid((0, 2, 1), (0, 2, 0))) == 1
    assert pf._vertex_ao_level(
        v, n, (1, 1, 1), grid((0, 2, 1), (1, 2, 0))) == 0
    # Interior vertex (e.g. a stair tread at 0.5): samples the cell
    # directly outside the vertex, not the edge neighbors.
    vi = (0.5, 1.0, 0.0)
    assert pf._vertex_ao_level(
        vi, n, (1, 1, 1), grid((1, 2, 1))) == 2
    assert pf._vertex_ao_level(
        vi, n, (1, 1, 1), grid((0, 2, 1))) == 3


def test_ao_occlusion_classification(assets_root):
    """Extended classifier checks (gap-2 dispatch mirror)."""
    tc: dict = {}
    occ = pf._block_occludes_ao
    # Full opaque cube / partial / transparent-texture cases.
    assert occ("test:test_cube", assets_root, tc) is True
    assert occ("test:test_glass", assets_root, tc) is False
    assert occ("test:test_slab", assets_root, tc) is False
    assert occ("test:test_stairs[facing=east]", assets_root, tc) is False
    # Leaves occlude even with a transparent texture (vanilla rule).
    assert occ("test:test_leaves", assets_root, tc) is True
    # Missing texture degrades to an opaque flat color -> occluding,
    # and the classifier must not raise.
    assert occ("test:test_notex", assets_root, tc) is True
    # Fluids / air / explicit non-occluding set (no assets needed).
    assert occ("minecraft:water", assets_root, tc) is False
    assert occ("minecraft:lava", assets_root, tc) is False
    assert occ("minecraft:air", assets_root, tc) is False
    assert occ("minecraft:ice", assets_root, tc) is False
    assert occ("minecraft:slime_block", assets_root, tc) is False
    assert occ("minecraft:honey_block", assets_root, tc) is False
    # Chest renders as a solid wooden box.
    assert occ("minecraft:chest", assets_root, tc) is True


def test_ao_tinted_leaves_composition():
    """AO composes with a (gap-1) pre-tinted texture: tint x AO on RGB,
    alpha untouched.

    Simulates gap-1's output by pre-tinting the texture in the test.
    The ±1 tolerance is float noise from the lstsq affine fit of the
    constant 0.4 field (truncation to uint8); a broken composition
    would be off by tens.
    """
    pts_uv = [(16, 0, 0, 0), (32, 16, 0, 16),
              (16, 32, 16, 16), (0, 16, 16, 0)]
    # Opaque pre-tinted texel: pixels must equal tint x 0.4 (±1).
    tex = Image.new("RGBA", (16, 16), (200, 100, 50, 255))
    c = Image.new("RGB", (32, 32), (255, 255, 255))
    pf._draw_textured_quad(c, pts_uv, tex, ao=(0.4, 0.4, 0.4, 0.4))
    r, g, b = c.load()[16, 16]
    assert abs(r - 80) <= 1 and abs(g - 40) <= 1 and abs(b - 20) <= 1, \
        f"want tint x 0.4 = (80,40,20) ±1, got {(r, g, b)}"
    # Translucent texel: alpha must not be dimmed by AO. With alpha=128
    # on a white canvas the blended result is (167,147,137) +/- 2; if AO
    # also multiplied alpha the result would be ~(220,212,208).
    tex2 = Image.new("RGBA", (16, 16), (200, 100, 50, 128))
    c2 = Image.new("RGB", (32, 32), (255, 255, 255))
    pf._draw_textured_quad(c2, pts_uv, tex2, ao=(0.4, 0.4, 0.4, 0.4))
    r, g, b = c2.load()[16, 16]
    assert abs(r - 167) <= 2 and abs(g - 147) <= 2 and abs(b - 137) <= 2, \
        f"alpha must be untouched by AO, got {(r, g, b)}"


def test_ao_entity_classification(assets_root):
    """The entity path of the classifier is merge-order independent.

    Pre-gap4 (no _try_entity_quads on the module) the entity step is
    skipped and both names fall through to the model/fallback path,
    matching the pre-gap4 render (magenta fallback cube -> occluding).
    Post-gap4 the hasattr guard activates: banners are thin cloth
    (non-occluding), the chest family is a near-full box (occluding).

    The hermetic fake assets ship no entity textures, so the test
    writes minimal 64x64 entity fakes first — without them the entity
    hook returns None and both names correctly degrade to the magenta
    fallback cube (occluding), which is the render-consistent answer
    but not the path this test pins.
    """
    tc: dict = {}
    if hasattr(pf, "_try_entity_quads"):
        # Minimal 64x64 entity fakes with vanilla-like transparent rounded
        # corners (fully-opaque fakes would load as RGB and never exercise
        # the corner-fill path).
        ent = assets_root / "textures" / "entity"
        (ent / "chest").mkdir(parents=True, exist_ok=True)
        (ent / "banner").mkdir(parents=True, exist_ok=True)
        trapped = Image.new("RGBA", (64, 64), (200, 200, 200, 255))
        trapped.putpixel((0, 0), (0, 0, 0, 0))
        trapped.putpixel((5, 0), (0, 0, 0, 0))
        trapped.save(ent / "chest" / "trapped.png")
        cloth = Image.new("RGBA", (64, 64), (240, 240, 240, 255))
        cloth.putpixel((0, 0), (0, 0, 0, 0))
        cloth.putpixel((41, 0), (0, 0, 0, 0))
        cloth.save(ent / "banner" / "banner_base.png")
        assert pf._block_occludes_ao(
            "minecraft:trapped_chest", assets_root, tc) is True
        assert pf._block_occludes_ao(
            "minecraft:white_banner", assets_root, tc) is False
    else:
        assert pf._block_occludes_ao(
            "minecraft:trapped_chest", assets_root, tc) is True
        assert pf._block_occludes_ao(
            "minecraft:white_banner", assets_root, tc) is True


def test_ao_deterministic(tmp_path, assets_root):
    """Two renders of a mixed grid -> identical PNG bytes (md5).

    NOTE: assets_dir is tmp_path (the fixture's parent); see
    test_ao_inner_corner_darkens for why the fixture value itself
    would render every block as the magenta fallback.
    """
    import hashlib
    import mcbuilder as mb
    digests = []
    for i in range(2):
        with mb.Build(seed=7) as b:
            for x in range(4):
                for z in range(4):
                    b.set(x, 0, z, "test:test_cube")
                    if (x + z) % 2 == 0:
                        b.set(x, 1, z, "test:test_cube")
                    if (x * z) % 3 == 0:
                        b.set(x, 2, z, "test:test_glass")
            out = tmp_path / f"run{i}"
            paths = b.render(out, views=["iso"], assets_dir=tmp_path,
                             tier="faithful", presentation=False, title=None)
        digests.append(hashlib.md5(paths[0].read_bytes()).hexdigest())
    assert digests[0] == digests[1], "AO render must be deterministic"


class _FakeGrid:
    """Duck-type of mcbuilder.voxels.VoxelGrid (mirrors test_preview.py)."""

    def __init__(self, arr, palette):
        self._arr = np.asarray(arr, dtype=np.int32)
        self._palette = list(palette)

    def to_dense(self):
        return self._arr, self._palette, {}


# Pre-AO baseline for test_ao_perf_smoke: median of 3 renders of the
# same 12x12x12 scene on main @ ab39e88 (pre-AO), presentation=False,
# single view, real assets, measured on this VM 2026-10-10 (1.28s;
# with-AO measured 1.86s = 1.45x in the same quiet period).
#
# DEVIATION from the plan's "< 2x" example: this VM's timing noise is
# large (shared container; identical with-AO code measured 1.86s quiet
# vs 2.45-3.5s under concurrent load — up to ~1.9x on NO code change),
# so a single-shot 2x bound flakes environmentally. The test instead
# warms up, takes best-of-3, and allows 2.5x: still catches any
# sustained algorithmic regression (best-of-3 filters spikes, not
# shifts) without failing on noise.
_AO_PERF_BASELINE_S = 1.28
_AO_PERF_BOUND = 2.5 * _AO_PERF_BASELINE_S


@needs_real_assets
def test_ao_perf_smoke(tmp_path):
    """AO render of a 12x12x12 mixed stone/air grid stays within the
    calibrated bound (best-of-3 after warmup; see _AO_PERF_BASELINE_S)."""
    import time
    arr = np.zeros((12, 12, 12), dtype=np.int32)
    for x in range(12):
        for y in range(12):
            for z in range(12):
                if (x * 7 + y * 13 + z * 5) % 3:
                    arr[x, y, z] = 1
    grid = _FakeGrid(arr, ["minecraft:air", "minecraft:stone"])
    views = parse_views("az045_el015")
    # Warmup (page cache, PIL/numpy init): not timed.
    pf.render(grid, str(tmp_path / "perf-warm"), views, _REAL_ROOT,
              presentation=False, title=None)
    best = min(
        _timed_render(grid, tmp_path / f"perf-{i}", views)
        for i in range(3)
    )
    assert best < _AO_PERF_BOUND, \
        f"AO render best-of-3 took {best:.1f}s, over the " \
        f"{_AO_PERF_BOUND:.1f}s bound (2.5x the {_AO_PERF_BASELINE_S}s " \
        f"pre-AO baseline)"


def _timed_render(grid, out_dir, views):
    import time
    t0 = time.perf_counter()
    pf.render(grid, str(out_dir), views, _REAL_ROOT,
              presentation=False, title=None)
    return time.perf_counter() - t0
