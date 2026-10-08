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
