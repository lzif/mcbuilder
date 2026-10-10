"""Waystone variant 4 — Skystead (7x7x7)."""

import mcbuilder as mb

import common

QB = "minecraft:quartz_block"
PR = "minecraft:prismarine_bricks"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=404, views=VIEWS)


def _floor(x, z):
    if 2 <= x <= 4 and 2 <= z <= 4:
        return QB
    if x in (0, 6) or z in (0, 6):
        return QB
    return PR


def _eave_lanterns():
    """Sea lanterns glowing under the roof eave, mid-point of each side."""
    g = mb.Geometry()
    for x, z in ((3, 0), (3, 6), (0, 3), (6, 3)):
        g.set(x, 4, z, "minecraft:sea_lantern")
    return g


def _base_trim():
    """Continuous prismarine band at y=2 along the platform edges,
    between the quartz pillars."""
    g = mb.Geometry()
    for i in (2, 3, 4):
        g.set(i, 2, 1, PR)
        g.set(i, 2, 5, PR)
        g.set(1, 2, i, PR)
        g.set(5, 2, i, PR)
    return g


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
    BUILD.place(_base_trim(), at=(0, 0, 0))
    BUILD.place(_eave_lanterns(), at=(0, 0, 0))
    BUILD.place(
        common.pedestal(
            pedestal_block=PR,
            hang_block="minecraft:sea_lantern",
        ),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.canopy(
            plate_slab="minecraft:quartz_slab[type=bottom]",
            eave_stair="minecraft:prismarine_stairs",
            corner_block=QB,
            cap_block=PR,
        ),
        at=(0, 0, 0),
    )
    # Overwrite y=6 cap: prismarine ring around quartz center (design top view;
    # the 3D render shows an apex sea lantern but the top view shows quartz —
    # the top view wins).
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            block = QB if (dx, dz) == (1, 1) else PR
            BUILD.set(x, 6, z, block)
