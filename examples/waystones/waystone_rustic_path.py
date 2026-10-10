"""Waystone variant 3 — Rustic Path (7x7x7)."""

import mcbuilder as mb

import common

SP = "minecraft:spruce_planks"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=303, views=VIEWS)


def _floor(x, z):
    return SP if x in (0, 6) or z in (0, 6) else "minecraft:cobblestone"


def _trapdoor_band():
    """Continuous trapdoor skirting at y=4 under the eave: full perimeter.

    Top-half panels read as one dark soffit band from every angle (the old
    per-pillar tabs read as disjointed shelves in iso).
    """
    g = mb.Geometry()
    for x in range(7):
        for z in range(7):
            if x in (0, 6) or z in (0, 6):
                if x == 0:
                    facing = "west"
                elif x == 6:
                    facing = "east"
                elif z == 0:
                    facing = "north"
                else:
                    facing = "south"
                g.set(
                    x, 4, z,
                    f"minecraft:spruce_trapdoor[facing={facing},half=top,open=false]",
                )
    return g


def _canopy():
    """Stepped pyramid roof: y=5 7x7 (stair eave + plank field), y=6 3x3
    stepped cap with stair shoulders and a plank crown."""
    g = mb.Geometry()
    field = mb.part.box(c1=(0, 0, 0), c2=(4, 0, 4), block=SP)
    for x, y, z, b in field.cells():
        g.set(x + 1, 5, z + 1, b)
    for i in range(1, 6):
        g.set(i, 5, 0, "minecraft:spruce_stairs[facing=north,half=bottom]")
        g.set(i, 5, 6, "minecraft:spruce_stairs[facing=south,half=bottom]")
        g.set(0, 5, i, "minecraft:spruce_stairs[facing=west,half=bottom]")
        g.set(6, 5, i, "minecraft:spruce_stairs[facing=east,half=bottom]")
    for cx, cz in ((0, 0), (0, 6), (6, 0), (6, 6)):
        g.set(cx, 5, cz, SP)
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            if (dx, dz) == (1, 1):
                g.set(x, 6, z, SP)
            elif (dx, dz) == (1, 0):
                g.set(x, 6, z, "minecraft:spruce_stairs[facing=north,half=bottom]")
            elif (dx, dz) == (1, 2):
                g.set(x, 6, z, "minecraft:spruce_stairs[facing=south,half=bottom]")
            elif (dx, dz) == (0, 1):
                g.set(x, 6, z, "minecraft:spruce_stairs[facing=west,half=bottom]")
            elif (dx, dz) == (2, 1):
                g.set(x, 6, z, "minecraft:spruce_stairs[facing=east,half=bottom]")
            else:
                g.set(x, 6, z, SP)
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
    BUILD.place(_trapdoor_band(), at=(0, 0, 0))
    # Short pedestal + framed, lit centerpiece: cobble base, waystone,
    # hanging lantern on a chain from the canopy.
    BUILD.set(3, 1, 3, "minecraft:cobblestone")
    BUILD.set(3, 2, 3, common.WAYSTONE)
    BUILD.set(3, 3, 3, "minecraft:lantern[hanging=true]")
    BUILD.set(3, 4, 3, "minecraft:iron_chain[axis=y]")
    BUILD.place(_canopy(), at=(0, 0, 0))
