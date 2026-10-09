"""Waystone variant 4 — Skystead (7x7x7)."""

import mcbuilder as mb

import common

QB = "minecraft:quartz_block"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=404, views=VIEWS)


def _floor(x, z):
    if 2 <= x <= 4 and 2 <= z <= 4:
        return QB
    if x in (0, 6) or z in (0, 6):
        return QB
    return "minecraft:prismarine_bricks"


with BUILD:
    BUILD.place(common.floor_pattern(fn=_floor), at=(0, 0, 0))
    BUILD.place(
        common.base_step(step_block=QB, stair_block="minecraft:quartz_stairs"),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.corner_lanterns(post_block=QB, lantern_block="minecraft:sea_lantern"),
        at=(0, 0, 0),
    )
    BUILD.place(common.pillars(pillar_block=QB), at=(0, 0, 0))
    BUILD.place(
        common.pedestal(
            pedestal_block="minecraft:prismarine_bricks",
            hang_block="minecraft:sea_lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.canopy(
            plate_slab="minecraft:quartz_slab[type=bottom]",
            eave_stair="minecraft:prismarine_stairs",
            corner_block=QB,
            cap_block="minecraft:prismarine_bricks",
        ),
        at=(0, 0, 0),
    )
    # Overwrite y=6 cap: prismarine ring around quartz center (design top view).
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            block = QB if (dx, dz) == (1, 1) else "minecraft:prismarine_bricks"
            BUILD.set(x, 6, z, block)
