"""Barn with a lean-to forge, hay-loft hoist and a ridge cupola.
Paste on flat ground; the foundation is y = 0..1. Main door faces south.
"""

import mcbuilder as mb

from common import BARN_WALL, FOUNDATION, HANGING_LANTERN, LANTERN, even_posts, gable_infill, window

BUILD = mb.Build(seed=1207, views="iso;az200_el025;az020_el030")

X0, X1, Z0, Z1 = 0, 10, 0, 8  # wall planes
MID = (X0 + X1) // 2
POST = "minecraft:stripped_spruce_log[axis=y]"

with BUILD:
    # -- shell: foundation, plank walls on a post frame, girt band at y = 5 ----------
    BUILD.box((X0 - 1, 0, Z0 - 1), (X1 + 1, 1, Z1 + 1), FOUNDATION)
    BUILD.box((X0, 1, Z0), (X1, 1, Z1), [("minecraft:spruce_planks", 2), "minecraft:coarse_dirt"])
    BUILD.walls((X0, 2, Z0), (X1, 8, Z1), BARN_WALL)
    xs, zs = even_posts(X0, X1), even_posts(Z0, Z1)
    BUILD.line((X0, 5, Z0), (X1, 5, Z0), "minecraft:spruce_log[axis=x]")
    BUILD.line((X0, 5, Z1), (X1, 5, Z1), "minecraft:spruce_log[axis=x]")
    BUILD.line((X0, 5, Z0), (X0, 5, Z1), "minecraft:spruce_log[axis=z]")
    BUILD.line((X1, 5, Z0), (X1, 5, Z1), "minecraft:spruce_log[axis=z]")
    for x in xs:
        for z in (Z0, Z1):
            BUILD.pillar((x, 2, z), 7, POST)
    for z in zs:
        for x in (X0, X1):
            BUILD.pillar((x, 2, z), 7, POST)

    # -- big south door with a framed opening -----------------------------------
    BUILD.carve((MID - 1, 2, Z1), (MID + 1, 5, Z1))
    for x in (MID - 2, MID + 2):
        BUILD.pillar((x, 2, Z1), 5, "minecraft:stripped_dark_oak_log[axis=y]")
    BUILD.line((MID - 2, 6, Z1), (MID + 2, 6, Z1), "minecraft:stripped_dark_oak_log[axis=x]")
    for x in (MID - 3, MID + 3):
        BUILD.pillar((x, 2, Z1 + 1), 2, "minecraft:spruce_fence")
        BUILD.set(x, 4, Z1 + 1, LANTERN)
    for x in (X0 + 2, X1 - 2):
        window(BUILD, x, 3, Z1, "south", flower_box=False)
    for z in (Z0 + 2, Z1 - 2):
        window(BUILD, X0, 3, z, "west", flower_box=False)

    # -- roof: gable end to the south, spruce band, wooden gable ends -------------
    BUILD.roof_gable(
        (X0 - 1, 9, Z0 - 1),
        (X1 + 1, 9, Z1 + 1),
        "minecraft:dark_oak_stairs",
        ridge="z",
        verge="minecraft:spruce_stairs",
        eave="minecraft:spruce_stairs",
    )
    for plane in (Z0, Z1):
        gable_infill(
            BUILD,
            plane,
            "z",
            9,
            X0 - 1,
            X1 + 1,
            kingpost=False,
            fill=[("minecraft:spruce_planks", 3), "minecraft:stripped_spruce_wood"],
            edge="minecraft:stripped_spruce_log",
        )

    # hay loft door with a hoist beam, chain and barrel
    BUILD.box((MID - 1, 10, Z1), (MID + 1, 11, Z1), "minecraft:air")
    BUILD.set(MID, 10, Z1, "minecraft:hay_block[axis=x]")
    BUILD.line((MID, 13, Z1 - 1), (MID, 13, Z1 + 2), "minecraft:stripped_spruce_log[axis=z]")
    BUILD.line((MID, 12, Z1 + 2), (MID, 10, Z1 + 2), "minecraft:iron_chain[axis=y]")
    BUILD.set(MID, 9, Z1 + 2, "minecraft:barrel[facing=up]")

    # ridge cupola: the one vertical accent on a long roof
    cz, ry = (Z0 + Z1) // 2, 15
    for dx in (-1, 1):
        for dz in (-1, 1):
            BUILD.pillar((MID + dx, ry, cz + dz), 2, POST)
    BUILD.box(
        (MID, ry, cz - 1),
        (MID, ry + 1, cz + 1),
        "minecraft:spruce_trapdoor[facing=east,half=bottom,open=true]",
    )
    BUILD.box((MID - 1, ry, cz), (MID + 1, ry + 1, cz), "minecraft:air")
    BUILD.set(MID, ry, cz, "minecraft:spruce_planks")
    BUILD.roof_hip(
        (MID - 2, ry + 2, cz - 2),
        (MID + 2, ry + 2, cz + 2),
        "minecraft:dark_oak_stairs",
        hip="minecraft:dark_oak_planks",
    )
    BUILD.set(MID, ry + 5, cz, "minecraft:lightning_rod[facing=up]")

    # -- interior: hay stack and storage ---------------------------------------------
    BUILD.box((X0 + 1, 2, Z0 + 1), (X0 + 3, 3, Z0 + 2), "minecraft:hay_block[axis=y]")
    for z in range(Z0 + 1, Z1 - 1):
        BUILD.set(
            X1 - 1,
            2,
            z,
            "minecraft:chest[facing=west]" if z % 2 else "minecraft:barrel[facing=west]",
        )
    BUILD.set(MID, 8, cz, HANGING_LANTERN)

    # -- lean-to forge on the east wall --------------------------------------------
    FX = X1 + 5
    BUILD.box((X1 + 1, 0, Z0 + 1), (FX, 1, Z1 - 1), FOUNDATION)
    BUILD.box(
        (X1 + 2, 1, Z0 + 2),
        (FX - 1, 1, Z1 - 2),
        [("minecraft:stone_bricks", 2), "minecraft:cobblestone", "minecraft:gravel"],
    )
    for z in (Z0 + 1, Z1 - 1):
        BUILD.pillar((FX, 2, z), 2, POST)
    for i, x in enumerate(range(FX, X1, -1)):  # lean-to roof climbs toward the barn
        BUILD.line(
            (x, 4 + i, Z0 + 1),
            (x, 4 + i, Z1 - 1),
            "minecraft:dark_oak_stairs[facing=west,half=bottom]",
        )
    for z in (Z0 + 1, Z1 - 1):
        BUILD.set(FX, 4, z, LANTERN)
        BUILD.set(FX, 5, z, "minecraft:dark_oak_slab[type=bottom]")
    tools = [
        "minecraft:blast_furnace[facing=east,lit=true]",
        "minecraft:anvil[facing=north]",
        "minecraft:grindstone[face=floor,facing=east]",
        "minecraft:smithing_table",
        "minecraft:lava_cauldron",
        "minecraft:stonecutter[facing=east]",
    ]
    for z, block in enumerate(tools, start=Z0 + 2):
        BUILD.set(X1 + 2, 2, z, block)
    BUILD.box((FX - 1, 2, Z0 + 2), (FX - 1, 3, Z0 + 2), "minecraft:barrel[facing=up]")
