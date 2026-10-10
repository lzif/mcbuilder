"""Waystone variant 1 — Classic Ruin (7x7x7)."""

import mcbuilder as mb

import common

SB = "minecraft:stone_bricks"
MSB = "minecraft:mossy_stone_bricks"
AND = "minecraft:polished_andesite"
VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=101, views=VIEWS)


def _mossy(x, z):
    """Organic moss scatter across ALL quadrants (~1/6 of cells)."""
    return MSB if (x * 5 + z * 3 + x * z) % 6 == 0 else SB


def _tier2():
    """3x3 second base tier at y=2: stair-tread edges, andesite center."""
    g = mb.Geometry()
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            if (dx, dz) == (1, 1):
                g.set(x, 2, z, AND)  # pedestal base / deliberate andesite accent
            elif (dx, dz) == (1, 0):
                g.set(x, 2, z, "minecraft:stone_brick_stairs[facing=south,half=bottom]")
            elif (dx, dz) == (1, 2):
                g.set(x, 2, z, "minecraft:stone_brick_stairs[facing=north,half=bottom]")
            elif (dx, dz) == (0, 1):
                g.set(x, 2, z, "minecraft:stone_brick_stairs[facing=east,half=bottom]")
            elif (dx, dz) == (2, 1):
                g.set(x, 2, z, "minecraft:stone_brick_stairs[facing=west,half=bottom]")
            else:
                g.set(x, 2, z, _mossy(x + 7, z + 3))
    return g


def _pillars():
    """Four pillars at (1,1),(1,5),(5,1),(5,5), y=2..4, moss on each."""
    g = mb.Geometry()
    for px, pz in ((1, 1), (1, 5), (5, 1), (5, 5)):
        for y in range(2, 5):
            g.set(px, y, pz, MSB if (px + pz + y) % 3 == 0 else SB)
    return g


def _rim_stair(x, z, facing):
    """Eave stair that keeps its shape but goes mossy along the roof rim."""
    if (x * 2 + z * 3) % 5 == 0:
        return f"minecraft:mossy_stone_brick_stairs[facing={facing},half=top]"
    return f"minecraft:stone_brick_stairs[facing={facing},half=top]"


def _canopy():
    """Canopy at y=5 (slab plate + stair eave with mossy rim), stepped cap at y=6."""
    g = mb.Geometry()
    plate = mb.part.box(c1=(0, 0, 0), c2=(4, 0, 4), block="minecraft:stone_brick_slab[type=bottom]")
    for x, y, z, b in plate.cells():
        g.set(x + 1, 5, z + 1, b)
    for i in (2, 3, 4):
        g.set(i, 5, 0, _rim_stair(i, 0, "north"))
        g.set(i, 5, 6, _rim_stair(i, 6, "south"))
        g.set(0, 5, i, _rim_stair(0, i, "west"))
        g.set(6, 5, i, _rim_stair(6, i, "east"))
    for cx, cz in ((0, 0), (0, 6), (6, 0), (6, 6)):
        g.set(cx, 5, cz, MSB if cx == cz else SB)
    for kx, kz in ((1, 0), (5, 0), (1, 6), (5, 6), (0, 1), (0, 5), (6, 1), (6, 5)):
        g.set(kx, 5, kz, _mossy(kx + 11, kz + 5))
    # y=6: stepped pyramid cap — full corners+center, stair shoulders, mossy flecks
    for dx in range(3):
        for dz in range(3):
            x, z = 2 + dx, 2 + dz
            if (dx, dz) == (1, 1):
                g.set(x, 6, z, SB)
            elif (dx, dz) in ((1, 0), (1, 2), (0, 1), (2, 1)):
                facing = {(1, 0): "south", (1, 2): "north", (0, 1): "east", (2, 1): "west"}[(dx, dz)]
                stair = (
                    "minecraft:mossy_stone_brick_stairs"
                    if (x + z) % 3 == 0
                    else "minecraft:stone_brick_stairs"
                )
                g.set(x, 6, z, f"{stair}[facing={facing},half=bottom]")
            else:
                g.set(x, 6, z, MSB if (x, z) in ((2, 4), (4, 2)) else SB)
    return g


with BUILD:
    BUILD.place(
        common.floor_pattern(fn=lambda x, z: _mossy(x, z)),
        at=(0, 0, 0),
    )
    BUILD.place(
        common.base_step(step_block=SB, stair_block="minecraft:stone_brick_stairs"),
        at=(0, 0, 0),
    )
    BUILD.place(_tier2(), at=(0, 0, 0))
    BUILD.place(
        common.corner_lanterns(post_block=SB, lantern_block="minecraft:lantern"),
        at=(0, 0, 0),
    )
    BUILD.place(_pillars(), at=(0, 0, 0))
    # Stepped, pronounced pedestal: andesite inlay (y=1) + andesite base (y=2,
    # via _tier2 center), waystone, hanging lantern.
    BUILD.set(3, 1, 3, AND)
    BUILD.place(
        common.pedestal(pedestal_block=AND, hang_block="minecraft:lantern"),
        at=(0, 0, 0),
    )
    BUILD.place(_canopy(), at=(0, 0, 0))
    chains = mb.part.pillar(height=2, block="minecraft:iron_chain[axis=y]")
    for cx, cz in ((2, 1), (4, 1), (2, 5), (4, 5)):
        BUILD.place(chains, at=(cx, 3, cz))
        BUILD.set(cx, 2, cz, "minecraft:lantern[hanging=true]")
