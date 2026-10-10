"""Waystone variant 2 — Dark Ritual (7x7x7)."""

import mcbuilder as mb

import common

DB = "minecraft:deepslate_bricks"
AM = "minecraft:amethyst_block"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=202, views=VIEWS)


def _floor(x, z):
    if (x, z) in ((0, 0), (0, 6), (6, 0), (6, 6), (3, 3)):
        return AM
    if x in (0, 6) or z in (0, 6):
        return "minecraft:blackstone"
    return "minecraft:deepslate_tiles"


def _corner_totems():
    """Corner posts y=1..4 (blackstone) with soul lanterns at y=2 AND y=5.

    y=2 = base glow (blueprint 3D); y=5 = roof-corner lanterns (blueprint top
    view). The y=5 lanterns occupy the canopy ring's corner cells.
    """
    g = mb.Geometry()
    for cx, cz in ((0, 0), (0, 6), (6, 0), (6, 6)):
        for y in range(1, 5):
            g.set(cx, y, cz, "minecraft:blackstone")
        g.set(cx, 2, cz, "minecraft:soul_lantern")
        g.set(cx, 5, cz, "minecraft:soul_lantern")
    return g


def _canopy():
    """Tiered roof: y=5 ring (stair eave, open corners) + plate; y=6 stepped
    3x3 with a SINGLE amethyst block at the center (blueprint top view)."""
    g = mb.Geometry()
    plate = mb.part.box(c1=(0, 0, 0), c2=(4, 0, 4), block="minecraft:blackstone_slab[type=bottom]")
    for x, y, z, b in plate.cells():
        g.set(x + 1, 5, z + 1, b)
    for i in (2, 3, 4):
        g.set(i, 5, 0, "minecraft:blackstone_stairs[facing=north,half=top]")
        g.set(i, 5, 6, "minecraft:blackstone_stairs[facing=south,half=top]")
        g.set(0, 5, i, "minecraft:blackstone_stairs[facing=west,half=top]")
        g.set(6, 5, i, "minecraft:blackstone_stairs[facing=east,half=top]")
    for kx, kz in ((1, 0), (5, 0), (1, 6), (5, 6), (0, 1), (0, 5), (6, 1), (6, 5)):
        g.set(kx, 5, kz, "minecraft:blackstone")
    # (ring corners left open — the totem lanterns sit there at y=5)
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            if (dx, dz) == (1, 1):
                g.set(x, 6, z, AM)
            elif (dx, dz) == (1, 0):
                g.set(x, 6, z, "minecraft:blackstone_stairs[facing=south,half=bottom]")
            elif (dx, dz) == (1, 2):
                g.set(x, 6, z, "minecraft:blackstone_stairs[facing=north,half=bottom]")
            elif (dx, dz) == (0, 1):
                g.set(x, 6, z, "minecraft:blackstone_stairs[facing=east,half=bottom]")
            elif (dx, dz) == (2, 1):
                g.set(x, 6, z, "minecraft:blackstone_stairs[facing=west,half=bottom]")
            else:
                g.set(x, 6, z, "minecraft:blackstone")
    return g


with BUILD:
    BUILD.place(common.floor_pattern(fn=_floor), at=(0, 0, 0))
    BUILD.place(
        common.base_step(
            step_block="minecraft:blackstone",
            stair_block="minecraft:blackstone_stairs",
        ),
        at=(0, 0, 0),
    )
    BUILD.set(3, 1, 3, AM)  # amethyst glow at the pedestal's base
    BUILD.place(_corner_totems(), at=(0, 0, 0))
    BUILD.place(common.pillars(pillar_block=DB), at=(0, 0, 0))
    # Amethyst spine: inlay plus around the pedestal, waystone, hanging crystal.
    for ix, iz in ((2, 3), (4, 3), (3, 2), (3, 4)):
        BUILD.set(ix, 2, iz, AM)
    BUILD.set(3, 2, 3, "minecraft:deepslate_tiles")
    BUILD.set(3, 3, 3, common.WAYSTONE)
    BUILD.set(3, 4, 3, AM)
    BUILD.place(_canopy(), at=(0, 0, 0))
