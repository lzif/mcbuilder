"""Waystone variant 1 — Classic Ruin (7x7x7)."""

import mcbuilder as mb

import common

SB = "minecraft:stone_bricks"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=101, views=VIEWS)

with BUILD:
    BUILD.place(
        common.floor_pattern(
            fn=lambda x, z: "minecraft:mossy_stone_bricks"
            if (x * 3 + z * 5) % 7 == 0
            else SB
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.base_step(step_block=SB, stair_block="minecraft:stone_brick_stairs"),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.corner_lanterns(post_block=SB, lantern_block="minecraft:lantern"),
        at=(0, 0, 0),
    )
    BUILD.place(common.pillars(pillar_block=SB), at=(0, 0, 0))
    BUILD.place(
        common.pedestal(
            pedestal_block="minecraft:polished_andesite",
            hang_block="minecraft:lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.canopy(
            plate_slab="minecraft:stone_brick_slab[type=bottom]",
            eave_stair="minecraft:stone_brick_stairs",
            corner_block=SB,
            cap_block=SB,
        ),
        at=(0, 0, 0),
    )
    chains = mb.part.pillar(height=2, block="minecraft:iron_chain[axis=y]")
    for cx, cz in ((2, 1), (4, 1), (2, 5), (4, 5)):
        BUILD.place(chains, at=(cx, 3, cz))
        BUILD.set(cx, 2, cz, "minecraft:lantern[hanging=true]")
