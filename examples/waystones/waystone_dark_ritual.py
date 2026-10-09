"""Waystone variant 2 — Dark Ritual (7x7x7)."""

import mcbuilder as mb

import common

VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=202, views=VIEWS)


def _floor(x, z):
    if (x, z) == (3, 3):
        return "minecraft:amethyst_block"
    if x in (0, 6) or z in (0, 6):
        return "minecraft:blackstone"
    return "minecraft:deepslate_tiles"


with BUILD:
    BUILD.place(common.floor_pattern(fn=_floor), at=(0, 0, 0))
    BUILD.place(
        common.base_step(
            step_block="minecraft:blackstone",
            stair_block="minecraft:blackstone_stairs",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.corner_lanterns(
            post_block="minecraft:blackstone",
            lantern_block="minecraft:soul_lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(common.pillars(pillar_block="minecraft:deepslate_bricks"), at=(0, 0, 0))
    BUILD.place(
        common.pedestal(
            pedestal_block="minecraft:deepslate_tiles",
            hang_block="minecraft:soul_lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.canopy(
            plate_slab="minecraft:blackstone_slab[type=bottom]",
            eave_stair="minecraft:blackstone_stairs",
            corner_block="minecraft:blackstone",
            cap_block="minecraft:deepslate_bricks",
        ),
        at=(0, 0, 0),
    )
