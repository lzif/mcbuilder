"""Waystone variant 3 — Rustic Path (7x7x7)."""

import mcbuilder as mb

import common

SP = "minecraft:spruce_planks"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=303, views=VIEWS)


def _floor(x, z):
    return SP if x in (0, 6) or z in (0, 6) else "minecraft:cobblestone"


def _trapdoors() -> mb.Geometry:
    """Skirting under the y=5 canopy edge: y=4, outward-facing, half=bottom.

    For each pillar at (px,pz), place trapdoors on the two outward faces
    (toward the 7x7 edge), at the non-pillar edge cells.
    """
    g = mb.Geometry()
    # (pillar, outward dir, trapdoor pos, facing)
    specs = [
        ((1, 1), (0, 4, 1), "west"),  ((1, 1), (1, 4, 0), "north"),
        ((1, 5), (0, 4, 5), "west"),  ((1, 5), (1, 4, 6), "south"),
        ((5, 1), (6, 4, 1), "east"),  ((5, 1), (5, 4, 0), "north"),
        ((5, 5), (6, 4, 5), "east"),  ((5, 5), (5, 4, 6), "south"),
    ]
    for _pillar, (x, y, z), facing in specs:
        g.set(x, y, z, f"minecraft:spruce_trapdoor[facing={facing},half=bottom,open=false]")
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
