"""Tests for the layer-by-layer build guide."""

from PIL import Image

import mcbuilder as mb
from mcbuilder.guide import item_counts, write_guide


def test_item_counts_skip_second_halves_and_double_slabs():
    counts = item_counts(
        [
            "minecraft:oak_door[half=lower]",
            "minecraft:oak_door[half=upper]",
            "minecraft:red_bed[part=foot]",
            "minecraft:red_bed[part=head]",
            "minecraft:stone_slab[type=double]",
            "minecraft:air",
            "minecraft:stone",
        ]
    )
    assert counts == {
        "minecraft:oak_door": 1,
        "minecraft:red_bed": 1,
        "minecraft:stone_slab": 2,
        "minecraft:stone": 1,
    }


def test_write_guide_one_image_per_non_empty_layer(tmp_path):
    b = mb.Build()
    with b:
        b.box((0, 0, 0), (3, 0, 3), "minecraft:stone")
        b.set(0, 2, 0, "minecraft:oak_stairs[facing=east]")  # y=1 stays empty
        b.set(1, 1, 1, "minecraft:air")
    md = write_guide(b.grid, tmp_path, None, title="Test")
    text = md.read_text()
    assert sorted(p.name for p in tmp_path.glob("layer-*.png")) == ["layer-01.png", "layer-02.png"]
    assert "| stone | 16 | 16 |" in text
    assert "## Layer 2 (y = 2)" in text
    assert Image.open(tmp_path / "layer-01.png").size[0] >= 720
