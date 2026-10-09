"""Waystone variant 3 — Rustic Path (7x7x7)."""

import mcbuilder as mb

import common

SP = "minecraft:spruce_planks"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=303, views=VIEWS)


def _floor(x, z):
    return SP if x in (0, 6) or z in (0, 6) else "minecraft:cobblestone"


def _trapdoors() -> mb.Geometry:
    g = mb.Geometry()
    for px, pz in ((1, 1), (1, 5), (5, 1), (5, 5)):
        g.set(px - 1, 3, pz, "minecraft:spruce_trapdoor[facing=west,half=bottom,open=false]")
        g.set(px + 1, 3, pz, "minecraft:spruce_trapdoor[facing=east,half=bottom,open=false]")
        g.set(px, 3, pz - 1, "minecraft:spruce_trapdoor[facing=north,half=bottom,open=false]")
        g.set(px, 3, pz + 1, "minecraft:spruce_trapdoor[facing=south,half=bottom,open=false]")
    return g


with BUILD:
    BUILD.place(common.floor_pattern(fn=_floor), at=(0, 0, 0))
    BUILD.place(
        common.base_step(
            step_block="minecraft:cobblestone",
            stair_block="minecraft:cobblestone_stairs",
            center_block="minecraft:cobblestone_slab[type=top]",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.corner_lanterns(post_block=SP, lantern_block="minecraft:lantern"),
        at=(0, 0, 0),
    )
    BUILD.place(common.pillars(pillar_block=SP), at=(0, 0, 0))
    BUILD.place(_trapdoors(), at=(0, 0, 0))
    BUILD.place(
        common.pedestal(
            pedestal_block="minecraft:cobblestone",
            hang_block="minecraft:lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.canopy(
            plate_slab="minecraft:spruce_slab[type=bottom]",
            eave_stair="minecraft:spruce_stairs",
            corner_block=SP,
            cap_block=SP,
        ),
        at=(0, 0, 0),
    )
