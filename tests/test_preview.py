"""Tests for mcbuilder.preview (PLAN section 4.4, fast tier).

Uses a minimal fake grid (the duck-type preview.py documents) so these
tests do not depend on the real VoxelGrid existing yet.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from mcbuilder.preview import RenderResult, render
from mcbuilder.views import parse_views


class FakeGrid:
    """Duck-type of mcbuilder.voxels.VoxelGrid as documented in preview.py."""

    def __init__(self, arr: np.ndarray, palette: list[str]):
        self._arr = np.asarray(arr, dtype=np.int32)
        self._palette = list(palette)

    def to_dense(self):
        return self._arr, self._palette, {}

    def bounds(self):
        occ = np.argwhere(self._arr != 0)
        if len(occ) == 0:
            return ((0, 0), (0, 0), (0, 0))
        lo = occ.min(axis=0)
        hi = occ.max(axis=0) + 1
        return ((int(lo[0]), int(hi[0])), (int(lo[1]), int(hi[1])),
                (int(lo[2]), int(hi[2])))


PALETTE = ["minecraft:air", "minecraft:stone",
           "minecraft:oak_log[axis=y]", "minecraft:glass"]


def make_grid() -> FakeGrid:
    arr = np.zeros((3, 3, 3), dtype=np.int32)
    arr[:, 0, :] = 1  # stone floor
    arr[1, 1, 1] = 2  # oak log pillar segment
    arr[1, 2, 1] = 2
    arr[0, 1, 0] = 3  # glass cube
    return FakeGrid(arr, PALETTE)


def make_assets(root: Path) -> Path:
    """Minimal fake vanilla asset tree: stone (cube_all) + oak_log (column)."""
    mc = root / "assets" / "1.21.4" / "client" / "assets" / "minecraft"
    (mc / "blockstates").mkdir(parents=True)
    (mc / "models" / "block").mkdir(parents=True)
    (mc / "textures" / "block").mkdir(parents=True)

    def write_json(path: Path, obj):
        path.write_text(json.dumps(obj), encoding="utf-8")

    def write_tex(name: str, color):
        Image.new("RGB", (16, 16), color).save(mc / "textures" / "block" / name)

    write_json(mc / "blockstates" / "stone.json",
               {"variants": {"": {"model": "minecraft:block/cube_all"}}})
    write_json(mc / "models" / "block" / "cube_all.json",
               {"parent": "minecraft:block/block",
                "textures": {"all": "minecraft:block/stone"}})
    write_json(mc / "models" / "block" / "block.json", {})
    write_tex("stone.png", (125, 125, 125))

    write_json(mc / "blockstates" / "oak_log.json",
               {"variants": {"axis=y": {"model": "minecraft:block/oak_log"},
                             "": {"model": "minecraft:block/oak_log"}}})
    write_json(mc / "models" / "block" / "oak_log.json",
               {"parent": "minecraft:block/cube_column",
                "textures": {"end": "minecraft:block/oak_log_top",
                             "side": "minecraft:block/oak_log"}})
    write_json(mc / "models" / "block" / "cube_column.json",
               {"parent": "minecraft:block/block"})
    write_tex("oak_log.png", (90, 70, 40))
    write_tex("oak_log_top.png", (150, 120, 70))
    # NOTE: no glass assets on purpose -> exercises the fallback path.
    return root / "assets"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_render_produces_named_pngs(tmp_path):
    grid = make_grid()
    views = parse_views("az045_el025;top")
    assets = make_assets(tmp_path)
    out = tmp_path / "previews"

    result = render(grid, out, views, assets)

    assert isinstance(result, RenderResult)
    assert [p.name for p in result] == ["az045_el025.png", "top.png"]
    for p in result:
        assert p.exists()
        with Image.open(p) as im:
            im.verify()
    # Longest side is 1024px.
    with Image.open(result[0]) as im:
        assert max(im.size) == 1024


def test_render_deterministic(tmp_path):
    grid = make_grid()
    views = parse_views("az045_el025;top")
    assets = make_assets(tmp_path)

    r1 = render(grid, tmp_path / "a", views, assets)
    r2 = render(grid, tmp_path / "b", views, assets)

    assert [file_hash(p) for p in r1] == [file_hash(p) for p in r2]


def test_missing_assets_falls_back_without_crashing(tmp_path):
    grid = make_grid()
    views = parse_views("az045_el025")
    out = tmp_path / "previews"

    result = render(grid, out, views, tmp_path / "does-not-exist")

    assert [p.name for p in result] == ["az045_el025.png"]
    assert result[0].exists()
    assert result.info["assets_missing"] is True
    assert result.info["assets_root"] is None
    # Every non-air block fell back to its hash color.
    assert sorted(result.info["fallback_blocks"]) == [
        "minecraft:glass", "minecraft:oak_log", "minecraft:stone",
    ]


def test_partial_assets_only_missing_blocks_fall_back(tmp_path):
    grid = make_grid()
    views = parse_views("top")
    assets = make_assets(tmp_path)

    result = render(grid, tmp_path / "previews", views, assets)

    assert result.info["assets_missing"] is False
    # stone + oak_log resolved from the fake tree; glass did not.
    assert result.info["fallback_blocks"] == ["minecraft:glass"]


def test_assets_dir_may_point_at_version_dir(tmp_path):
    grid = make_grid()
    views = parse_views("top")
    assets = make_assets(tmp_path)
    version_dir = assets / "1.21.4"

    result = render(grid, tmp_path / "previews", views, version_dir)

    assert result.info["assets_missing"] is False


def test_empty_grid_renders_without_crashing(tmp_path):
    grid = FakeGrid(np.zeros((4, 4, 4), dtype=np.int32), ["minecraft:air"])
    views = parse_views("iso")
    result = render(grid, tmp_path / "previews", views, None)
    assert result[0].exists()
    with Image.open(result[0]) as im:
        im.verify()


def test_fallback_color_is_hash_based():
    # Same name -> same color, every run (md5, not builtin hash).
    from mcbuilder.preview import _fallback_color
    c1 = _fallback_color("minecraft:glass")
    c2 = _fallback_color("minecraft:glass")
    assert c1 == c2
    assert c1 == tuple(hashlib.md5(b"minecraft:glass").digest()[:3])
    assert _fallback_color("minecraft:stone") != c1


def _write_json(path: Path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_tex(mc: Path, name: str, color):
    Image.new("RGB", (16, 16), color).save(mc / "textures" / "block" / name)


def test_bare_blockstate_without_default_variant_resolves(tmp_path):
    # Real vanilla blockstates (e.g. oak_log) ship NO empty-key default
    # variant. A bare palette entry (no props) must still resolve via the
    # vanilla default props (axis=y), not degrade to the fallback color.
    mc = tmp_path / "assets" / "x" / "client" / "assets" / "minecraft"
    (mc / "blockstates").mkdir(parents=True)
    (mc / "models" / "block").mkdir(parents=True)
    (mc / "textures" / "block").mkdir(parents=True)
    _write_json(mc / "blockstates" / "oak_log.json",
                {"variants": {
                    "axis=x": {"model": "minecraft:block/oak_log"},
                    "axis=y": {"model": "minecraft:block/oak_log"},
                    "axis=z": {"model": "minecraft:block/oak_log"}}})
    _write_json(mc / "models" / "block" / "oak_log.json",
                {"parent": "minecraft:block/cube_column",
                 "textures": {"end": "minecraft:block/oak_log_top",
                              "side": "minecraft:block/oak_log"}})
    _write_json(mc / "models" / "block" / "cube_column.json",
                {"parent": "minecraft:block/block"})
    _write_tex(mc, "oak_log.png", (90, 70, 40))
    _write_tex(mc, "oak_log_top.png", (150, 120, 70))

    arr = np.zeros((2, 2, 2), dtype=np.int32)
    arr[0, 0, 0] = 1
    grid = FakeGrid(arr, ["minecraft:air", "minecraft:oak_log"])  # no props
    result = render(grid, tmp_path / "previews", parse_views("top"),
                    tmp_path / "assets")
    assert result.info["fallback_blocks"] == []


def test_bare_snowy_blockstate_resolves_to_snowy_false(tmp_path):
    # grass_block / mycelium / podzol key their variants on snowy=
    # (the only three blockstates in 26.2 that do). A bare palette entry
    # must resolve via the snowy=false default, not magenta-cube.
    from mcbuilder import preview as _fast
    assert _fast._DEFAULT_PROPS["snowy"] == "false"
    mc = tmp_path / "assets" / "x" / "client" / "assets" / "minecraft"
    (mc / "blockstates").mkdir(parents=True)
    (mc / "models" / "block").mkdir(parents=True)
    (mc / "textures" / "block").mkdir(parents=True)
    _write_json(mc / "blockstates" / "test_grass.json",
                {"variants": {
                    "snowy=false": {"model": "minecraft:block/test_grass"},
                    "snowy=true": {"model": "minecraft:block/test_grass_snow"}}})
    _write_json(mc / "models" / "block" / "test_grass.json",
                {"parent": "minecraft:block/cube_all",
                 "textures": {"all": "minecraft:block/test_grass_tex"}})
    _write_json(mc / "models" / "block" / "test_grass_snow.json",
                {"parent": "minecraft:block/cube_all",
                 "textures": {"all": "minecraft:block/test_grass_snow_tex"}})
    _write_tex(mc, "test_grass_tex.png", (100, 150, 60))
    _write_tex(mc, "test_grass_snow_tex.png", (230, 240, 245))

    arr = np.zeros((2, 2, 2), dtype=np.int32)
    arr[0, 0, 0] = 1
    grid = FakeGrid(arr, ["minecraft:air", "minecraft:test_grass"])  # no props
    result = render(grid, tmp_path / "previews", parse_views("top"),
                    tmp_path / "assets")
    assert result.info["fallback_blocks"] == []
    # The snowy=false (green) texture won, not the snowy=true (snow) one.
    img = Image.open(tmp_path / "previews" / "top.png")
    assert img.getpixel((img.size[0] // 2, img.size[1] // 2))[:3] != (230, 240, 245)


def test_non_cube_model_maps_single_texture_var(tmp_path):
    # Fence/torch-style models are not cube templates and expose a single
    # texture var (``texture``/``torch``). The fast tier must map faces to
    # it rather than render a flat fallback color.
    mc = tmp_path / "assets" / "x" / "client" / "assets" / "minecraft"
    (mc / "blockstates").mkdir(parents=True)
    (mc / "models" / "block").mkdir(parents=True)
    (mc / "textures" / "block").mkdir(parents=True)
    _write_json(mc / "blockstates" / "oak_fence.json",
                {"multipart": [{"apply": {"model": "minecraft:block/fence_post"}}]})
    _write_json(mc / "models" / "block" / "fence_post.json",
                {"parent": "minecraft:block/fence_post",
                 "textures": {"texture": "minecraft:block/oak_planks"}})
    _write_json(mc / "models" / "block" / "fence_inventory.json", {})
    _write_tex(mc, "oak_planks.png", (140, 110, 70))

    arr = np.zeros((2, 2, 2), dtype=np.int32)
    arr[0, 0, 0] = 1
    grid = FakeGrid(arr, ["minecraft:air", "minecraft:oak_fence"])
    result = render(grid, tmp_path / "previews", parse_views("top"),
                    tmp_path / "assets")
    assert result.info["fallback_blocks"] == []


# ---------------------------------------------------------------------------
# gap4 fast tier: honest flat colors for block entities + fallback_blocks
# behavior change (water/lava leave fallback_blocks — intentional
# approximations are not missing-asset warnings)
# ---------------------------------------------------------------------------

def _resolved_mc_root(tmp_path):
    from mcbuilder.preview import _resolve_assets_root
    root = _resolve_assets_root(make_assets(tmp_path))
    assert root is not None
    return root


def test_fast_chest_flat_color(tmp_path):
    from mcbuilder.preview import _build_face_textures
    assets = _resolved_mc_root(tmp_path)
    fb: set = set()
    faces = _build_face_textures("minecraft:chest", assets, fb)
    assert faces["north"].getpixel((0, 0)) == (181, 140, 82)
    assert "minecraft:chest" not in fb


def test_fast_trapped_chest_flat_color(tmp_path):
    from mcbuilder.preview import _build_face_textures
    assets = _resolved_mc_root(tmp_path)
    fb: set = set()
    faces = _build_face_textures("minecraft:trapped_chest", assets, fb)
    assert faces["north"].getpixel((0, 0)) == (170, 110, 75)
    assert "minecraft:trapped_chest" not in fb


def test_fast_banner_flat_color(tmp_path):
    from mcbuilder.preview import _build_face_textures
    assets = _resolved_mc_root(tmp_path)
    fb: set = set()
    faces = _build_face_textures("minecraft:red_banner", assets, fb)
    assert faces["north"].getpixel((0, 0)) == (176, 46, 38)
    assert "minecraft:red_banner" not in fb
    faces = _build_face_textures("minecraft:white_wall_banner[facing=north]",
                                 assets, fb)
    assert faces["north"].getpixel((0, 0)) == (249, 255, 254)
    assert "minecraft:white_wall_banner" not in fb


def test_fast_fluid_no_warning(tmp_path):
    """water/lava are intentional flat approximations — no fallback entry."""
    from mcbuilder.preview import _build_face_textures
    assets = make_assets(tmp_path)
    fb: set = set()
    faces = _build_face_textures("minecraft:water", assets, fb)
    # gap1 biome tint moved fast-tier water to vanilla's default water
    # color 0x3F76E4 (was the older (52, 120, 235) flat approximation).
    assert faces["north"].getpixel((0, 0)) == (63, 118, 228)
    faces = _build_face_textures("minecraft:lava", assets, fb)
    assert faces["north"].getpixel((0, 0)) == (255, 110, 20)
    assert "minecraft:water" not in fb
    assert "minecraft:lava" not in fb
