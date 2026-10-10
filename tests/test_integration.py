"""Cross-component integration tests for mcbuilder.

These exercise the seams between components with the REAL implementations
(no duck-type fakes): real ``Build``/``VoxelGrid`` -> ``to_dense()`` ->
preview renderer. They pin the contract the unit tests mock:

- ``to_dense()`` uses ``-1`` (UNSET) for never-placed cells inside the bbox;
- air's palette index is wherever the grid interned it (NOT assumed 0);
- the renderer must skip both, and must not drop the bbox's max layer.

The first two tests would have caught the integration bugs found during the
coordinator's integration pass (UNSET cells rendered as ``palette[-1]``;
blocks at palette index 0 never drawn; world-coord bounds mis-cropping).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import mcbuilder as mb
from mcbuilder.preview import _crop_bounds, _renderable_mask, _BG
from mcbuilder.views import parse_views


# ---------------------------------------------------------------------------
# renderable-mask / crop contract
# ---------------------------------------------------------------------------


def test_renderable_mask_skips_unset_and_carved_air_anywhere_in_palette():
    # air interned at index 2 (not 0); -1 = UNSET
    palette = ["minecraft:stone", "minecraft:oak_planks", "minecraft:air"]
    arr = np.array([[[0, -1], [2, 1]]], dtype=np.int32)
    mask = _renderable_mask(arr, palette)
    assert mask.tolist() == [[[True, False], [False, True]]]


def test_renderable_mask_without_air_in_palette():
    palette = ["minecraft:stone", "minecraft:dirt"]
    arr = np.array([[[-1, 0], [1, -1]]], dtype=np.int32)
    mask = _renderable_mask(arr, palette)
    assert mask.tolist() == [[[False, True], [True, False]]]


def test_crop_bounds_tight_over_renderable_cells():
    palette = ["minecraft:stone", "minecraft:oak_planks", "minecraft:air"]
    arr = np.full((4, 4, 4), -1, dtype=np.int32)
    arr[1, 1, 1] = 0   # stone
    arr[2, 2, 2] = 1   # planks
    arr[3, 3, 3] = 2   # carved air must not extend the crop
    assert _crop_bounds(arr, palette) == ((1, 3), (1, 3), (1, 3))


def test_crop_bounds_none_when_nothing_renderable():
    palette = ["minecraft:air"]
    arr = np.full((2, 2, 2), -1, dtype=np.int32)
    assert _crop_bounds(arr, palette) is None


# ---------------------------------------------------------------------------
# end-to-end: real Build -> build.render()
# ---------------------------------------------------------------------------


def _non_bg_pixels(path: Path) -> int:
    img = Image.open(path).convert("RGB")
    data = np.asarray(img)
    return int(np.any(data != np.array(_BG, dtype=np.uint8), axis=-1).sum())


def test_end_to_end_hollow_box_offset_origin(tmp_path):
    """Hollow walls-box built away from the origin, stone placed first
    (palette index 0), carved air inside afterwards (air at a later index).

    Guards: every palette index renders (incl. 0), UNSET interior cells and
    carved air render as nothing, the max bbox layer is not cropped away,
    and rendering is deterministic.
    """
    b = mb.Build(seed=7)
    with b:
        # offset from origin on purpose: the old world-coord crop path
        # mis-framed any build not starting at (0, 0, 0)
        b.walls((10, 5, -8), (14, 9, -4), "minecraft:stone")
        b.set(12, 7, -6, "minecraft:air")  # carved air, later palette index
    out1 = tmp_path / "r1"
    paths1 = b.render(out1, views=["top", "iso"])
    assert [p.name for p in paths1] == ["top.png", "iso.png"]
    for p in paths1:
        assert p.is_file()
        # far more than a placeholder: real geometry was drawn
        assert _non_bg_pixels(p) > 5000, p.name

    # determinism: same build + same views => byte-identical PNGs
    out2 = tmp_path / "r2"
    paths2 = b.render(out2, views=["top", "iso"])
    for p1, p2 in zip(paths1, paths2):
        assert p1.read_bytes() == p2.read_bytes()


def test_colon_style_views_from_plan_example(tmp_path):
    """PLAN section 4.5's own example uses ``orbit:8_el:25`` — it must work."""
    assert [v.label for v in parse_views("orbit:8_el:25;top")][:2] == [
        "az000_el025",
        "az045_el025",
    ]
    b = mb.Build(seed=3, views=["orbit:8_el:25", "top"])
    with b:
        b.box((0, 0, 0), (3, 2, 3), "minecraft:oak_planks")
    paths = b.render(tmp_path / "colon")
    assert len(paths) == 9
    assert paths[0].name == "az000_el025.png"
    assert paths[-1].name == "top.png"


def test_build_render_view_precedence(tmp_path):
    b = mb.Build(seed=1, views=["top"])
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    # explicit argument beats script config
    paths = b.render(tmp_path / "a", views=["iso"])
    assert [p.name for p in paths] == ["iso.png"]
    # script config beats the default 9-view set
    paths = b.render(tmp_path / "b")
    assert [p.name for p in paths] == ["top.png"]
    # default when nothing configured
    b2 = mb.Build(seed=1)
    with b2:
        b2.set(0, 0, 0, "minecraft:stone")
    assert len(b2.render(tmp_path / "c")) == 9


# ---------------------------------------------------------------------------
# parts as Build methods (PLAN section 4.5 usage: BUILD.stairs_run(...))
# ---------------------------------------------------------------------------


def test_parts_methods_place_expected_cells_with_provenance():
    b = mb.Build(seed=11)
    with b:
        b.stairs_run((0, 0, 0), "north", 3, "minecraft:stone_brick_stairs")
        b.pillar((5, 0, 5), 3, "minecraft:oak_log[axis=y]")
        b.railing((0, 4, 0), (2, 4, 0), "minecraft:oak_fence")
    grid = b.grid
    # stairs ascend north (-z), tall backs uphill (facing north)
    arr, palette, provenance = grid.to_dense()
    stair_idx = next(
        i for i, s in enumerate(palette) if s.startswith("minecraft:stone_brick_stairs")
    )
    assert "facing=north" in palette[stair_idx]
    assert "half=bottom" in palette[stair_idx]
    # 3 steps + 3 pillar + 3 railing = 9 non-air cells
    assert grid.count_non_air() == 9
    # every palette entry carries file:line provenance
    assert set(provenance) == set(range(len(palette)))
    f, line = provenance[stair_idx]
    assert f == __file__ and isinstance(line, int)


def test_parts_module_functions_still_work_directly():
    b = mb.Build(seed=11)
    with b:
        mb.parts.pillar(b, (0, 0, 0), 2, "minecraft:stone")
    assert b.grid.count_non_air() == 2


# ---------------------------------------------------------------------------
# full CLI pipeline with the plan-example surface (colon views + parts)
# ---------------------------------------------------------------------------

HANDMADE_BLOCKS = {
    "minecraft:stone": {"properties": {}},
    "minecraft:oak_planks": {"properties": {}},
    "minecraft:stone_brick_stairs": {
        "properties": {"facing": ["north", "south", "east", "west"],
                       "half": ["top", "bottom"]}
    },
    "minecraft:air": {"properties": {}},
}

SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["orbit:8_el:25", "top"])

with BUILD:
    BUILD.box((0, 0, 0), (4, 2, 4), "minecraft:oak_planks")
    BUILD.stairs_run((0, 3, 0), "east", 3, "minecraft:stone_brick_stairs")
"""


@pytest.fixture(autouse=True)
def _pin_hashseed(monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "0")


def test_cli_run_end_to_end(tmp_path, monkeypatch):
    from mcbuilder.cli import main
    from mcbuilder.registry import Registry

    reg = Registry(HANDMADE_BLOCKS, "test")
    monkeypatch.setattr(
        Registry, "load", classmethod(lambda cls, version, cache_dir: reg)
    )
    script = tmp_path / "hut.py"
    script.write_text(SCRIPT)
    out = tmp_path / "dist"

    rc = main(["run", str(script), "--out", str(out), "--preview"])
    assert rc == 0

    run_dir = out / "run-001"
    report = json.loads((run_dir / "report.json").read_text())
    assert report["errors"] == []
    # All three tiers render: 9 fast + 9 trusted + 9 faithful.
    assert len(report["views"]) == 27
    assert report["views"][0]["file"] == "previews/az000_el025.png"
    assert report["views"][0]["label"] == "az000_el025"
    assert report["views"][-1]["file"] == "previews_faithful/top.png"
    fast = report["views"][:9]
    trusted = report["views"][9:18]
    faithful = report["views"][18:]
    assert all(v["directions_untrusted"] and not v["directions_trusted"] for v in fast)
    assert all(v["directions_trusted"] and not v["directions_untrusted"] for v in trusted)
    assert all(v["file"].startswith("previews_trusted/") for v in trusted)
    assert all(v["directions_trusted"] and not v["directions_untrusted"] for v in faithful)
    assert all(v["file"].startswith("previews_faithful/") for v in faithful)
    # block_counts is the survival shopping list: post-crop, air excluded
    assert report["block_counts"]["minecraft:oak_planks"] == 5 * 3 * 5
    assert report["block_counts"]["minecraft:stone_brick_stairs[facing=east,half=bottom]"] == 3
    assert "minecraft:air" not in report["block_counts"]
    previews = sorted((run_dir / "previews").glob("*.png"))
    assert len(previews) == 9
