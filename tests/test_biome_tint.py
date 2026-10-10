"""Tests for biome tint (plains default) in both preview tiers (gap1).

Hermetic: all fake models/textures come from conftest's ``make_assets``
(solid colors, so pixel assertions are exact). Table entries for the
``test:``-namespace blocks are injected via monkeypatch (auto-restored);
both tiers read ``_TINT_TABLE`` at call time.
"""

import numpy as np
import pytest
from PIL import Image

from mcbuilder import preview as _fast
from mcbuilder import preview_faithful as pf


def _mul(c, m):
    """Exact per-channel multiply the code performs: int(c * m).

    ``m`` may be a scalar shade factor or a per-channel tuple.
    """
    if isinstance(m, (int, float)):
        m = (m, m, m)
    return tuple(int(v * mm) for v, mm in zip(c, m))


def _tint(c, tint):
    return _mul(c, (t / 255.0 for t in tint))


def _mean(img):
    a = np.asarray(img.convert("RGB"), dtype=np.float64).reshape(-1, 3)
    return tuple(a.mean(axis=0).round(1))


def _close(actual, expected, tol=2.0):
    return all(abs(a - e) <= tol for a, e in zip(actual, expected))


def _up_quad_mean(quads):
    for _pts, n, img in quads:
        if n == (0, 1, 0):
            return _mean(img)
    raise AssertionError("no up quad")


# ---------------------------------------------------------------------------
# 1. pinned table values (26.2-verified)
# ---------------------------------------------------------------------------

def test_pinned_table_values():
    assert _fast._TINT_TABLE["minecraft:grass_block"] == (145, 189, 89)
    assert _fast._TINT_TABLE["minecraft:oak_leaves"] == (119, 171, 47)
    assert _fast._TINT_TABLE["minecraft:leaf_litter"] == (163, 117, 70)
    assert _fast._TINT_TABLE["minecraft:birch_leaves"] == (128, 167, 85)
    assert _fast._TINT_TABLE["minecraft:spruce_leaves"] == (97, 153, 97)
    assert _fast._TINT_TABLE["minecraft:lily_pad"] == (32, 128, 48)
    assert _fast._PLAINS_WATER == (63, 118, 228)
    assert _fast._FLUID_FLAT["minecraft:water"] == (63, 118, 228)


# ---------------------------------------------------------------------------
# 2. faithful overlay disambiguation (grass-block analog)
# ---------------------------------------------------------------------------

def test_faithful_tints_only_tintindex_faces(assets_root, monkeypatch):
    tint = (100, 150, 200)
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_overlay", tint)
    fb_blocks = set()
    quads, fb = pf.resolve_block_quads(
        "test:test_tint_overlay", assets_root, {}, fb_blocks)
    assert fb is False
    assert fb_blocks == set()

    north = [q for q in quads if q[1] == (0, 0, -1)]
    assert len(north) == 2  # one #side + one #overlay element face
    means = sorted(_mean(q[2]) for q in north)

    exp_tinted = _mul(_tint((160, 160, 160), tint), 0.8)  # north shade
    exp_raw = _mul((210, 210, 210), 0.8)
    assert _close(means[0], exp_tinted), (means[0], exp_tinted)
    assert _close(means[1], exp_raw), (means[1], exp_raw)


# ---------------------------------------------------------------------------
# 3. faithful leaves analog + per-block (not per-texture) lookup
# ---------------------------------------------------------------------------

def test_faithful_tints_all_cube_faces(assets_root, monkeypatch):
    tint = (100, 150, 200)
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube", tint)
    quads, fb = pf.resolve_block_quads(
        "test:test_tint_cube", assets_root, {}, set())
    assert fb is False
    assert len(quads) == 6

    base = _tint((200, 200, 200), tint)
    for _pts, n, img in quads:
        assert _close(_mean(img), _mul(base, pf._SHADES[n])), (n, _mean(img))


def test_faithful_tint_is_per_block_not_per_texture(assets_root, monkeypatch):
    # test_tint_cube and test_tint_cube_b share the same texture file.
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube", (100, 150, 200))
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube_b", (10, 20, 30))
    quads_a, _ = pf.resolve_block_quads(
        "test:test_tint_cube", assets_root, {}, set())
    quads_b, _ = pf.resolve_block_quads(
        "test:test_tint_cube_b", assets_root, {}, set())
    assert _up_quad_mean(quads_a) != _up_quad_mean(quads_b)
    assert _close(_up_quad_mean(quads_a), _tint((200, 200, 200), (100, 150, 200)))
    assert _close(_up_quad_mean(quads_b), _tint((200, 200, 200), (10, 20, 30)))


# ---------------------------------------------------------------------------
# 4. untinted controls (default-deny)
# ---------------------------------------------------------------------------

def test_faithful_untinted_controls(assets_root):
    # No tintindex and no table entry.
    quads, fb = pf.resolve_block_quads(
        "test:test_tint_plain", assets_root, {}, set())
    assert fb is False
    assert _close(_up_quad_mean(quads), (120, 120, 120), tol=0.5)

    # tintindex 0 inherited from the parent model, but no table entry
    # (cherry/pale-oak leaves analog): stays untinted.
    quads, fb = pf.resolve_block_quads(
        "test:test_tint_cherry", assets_root, {}, set())
    assert fb is False
    assert _close(_up_quad_mean(quads), (180, 140, 140), tol=0.5)


# ---------------------------------------------------------------------------
# 5. cache isolation
# ---------------------------------------------------------------------------

def test_tint_never_mutates_tex_cache(assets_root, monkeypatch, tex_cache):
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube", (100, 150, 200))
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube_b", (10, 20, 30))
    quads_a, _ = pf.resolve_block_quads(
        "test:test_tint_cube", assets_root, tex_cache, set())
    quads_b, _ = pf.resolve_block_quads(
        "test:test_tint_cube_b", assets_root, tex_cache, set())

    # Cached source image is byte-identical to the raw PNG.
    cached = tex_cache["block/tint_gray"]
    with Image.open(assets_root / "textures" / "block" / "tint_gray.png") as raw:
        assert np.array_equal(np.asarray(cached), np.asarray(raw.convert("RGB")))

    # ...while the two blocks' quad textures differ.
    assert _up_quad_mean(quads_a) != _up_quad_mean(quads_b)


# ---------------------------------------------------------------------------
# 6. fast tier
# ---------------------------------------------------------------------------

def test_fast_tier_tints_and_skips_untinted_vars(assets_root, monkeypatch):
    tint = (100, 150, 200)
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_cube", tint)
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_overlay", tint)

    fb = set()
    faces = _fast._build_face_textures("test:test_tint_cube", assets_root, fb)
    assert fb == set()
    assert _close(_mean(faces["up"]), _tint((200, 200, 200), tint), tol=0.5)

    # tinted_vars == {"overlay"} here, but the fast tier's face->var rule
    # maps "up" to "side", which is not tinted -> stays raw.
    images, _leaf, tinted_vars = _fast._resolve_model_textures(
        "test:test_tint_overlay", {}, assets_root)
    assert tinted_vars == {"overlay"}
    faces = _fast._build_face_textures(
        "test:test_tint_overlay", assets_root, set())
    assert _close(_mean(faces["up"]), (210, 210, 210), tol=0.5)


def test_fast_tier_water_fallback_color():
    assert _fast._fallback_color("minecraft:water") == (63, 118, 228)


# ---------------------------------------------------------------------------
# 7. water (faithful tier fluid path)
# ---------------------------------------------------------------------------

def test_faithful_water_pixel(assets_root):
    quads, fb = pf.resolve_block_quads("minecraft:water", assets_root, {})
    assert fb is False
    for _pts, n, img in quads:
        if n == (0, 1, 0):  # top face, shade 1.0
            assert img.mode == "RGBA"
            assert img.getpixel((0, 0)) == (63, 118, 228, 150)
            return
    raise AssertionError("no top quad")


# ---------------------------------------------------------------------------
# 8. tintindex:1 gating (wildflowers/flowerbed analog)
# ---------------------------------------------------------------------------

def test_faithful_tintindex_1_tints(assets_root, monkeypatch):
    tint = (100, 150, 200)
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_index1", tint)
    quads, fb = pf.resolve_block_quads(
        "test:test_tint_index1", assets_root, {}, set())
    assert fb is False
    # Gating is >= 0, not == 0.
    assert _close(_up_quad_mean(quads), _tint((170, 170, 170), tint), tol=0.5)


# ---------------------------------------------------------------------------
# 9. fast-tier bamboo limitation (documented, pinned)
# ---------------------------------------------------------------------------

def test_fast_tier_bamboo_limitation(assets_root, monkeypatch):
    # test_tint_multi mirrors real bamboo.json ordering: the untinted
    # stalk apply comes first, the tinted leaf apply second.
    monkeypatch.setitem(_fast._TINT_TABLE, "test:test_tint_multi", (100, 150, 200))
    _images, _leaf, tinted_vars = _fast._resolve_model_textures(
        "test:test_tint_multi", {}, assets_root)
    assert tinted_vars == set()

    faces = _fast._build_face_textures(
        "test:test_tint_multi", assets_root, set())
    # Stalk-only, untinted: raw (140,140,140).
    assert _close(_mean(faces["up"]), (140, 140, 140), tol=0.5)
