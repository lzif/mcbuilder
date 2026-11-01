"""Stone watchtower: 5 x 5 shaft, belt course, corbelled crenellated parapet,
turret roof on posts. Paste on flat ground; the foundation is y = 0.
"""

import mcbuilder as mb

from common import FOUNDATION, LANTERN, ROOF

BUILD = mb.Build(seed=1207, views="iso;az200_el025;top")

X0, X1, Z0, Z1 = 0, 4, 0, 4
CX, CZ = 2, 2
TOP = 16  # last wall layer


def aged_stone(x, y, z):
    """Mossier near the ground, cleaner toward the top."""
    r = BUILD.rng(f"stone {x},{y},{z}").random()
    moss = 0.45 * (1 - y / TOP)
    if r < moss:
        return "minecraft:mossy_stone_bricks"
    if r < moss + 0.12:
        return "minecraft:cracked_stone_bricks"
    return "minecraft:stone_bricks"


with BUILD:
    BUILD.box((X0 - 1, 0, Z0 - 1), (X1 + 1, 0, Z1 + 1), FOUNDATION)
    BUILD.walls((X0, 1, Z0), (X1, TOP, Z1), aged_stone)
    BUILD.box((X0 + 1, 1, Z0 + 1), (X1 - 1, 1, Z1 - 1), "minecraft:spruce_planks")

    # belt course halfway up
    BUILD.walls((X0 - 1, 8, Z0 - 1), (X1 + 1, 8, Z1 + 1), "minecraft:stone_brick_slab[type=top]")

    # arrow slits, door, ladder
    for y in (5, 11):
        for x, z, face in (
            (CX, Z0, "north"),
            (CX, Z1, "south"),
            (X0, CZ, "west"),
            (X1, CZ, "east"),
        ):
            if not (face == "south" and y == 5):
                BUILD.pillar((x, y, z), 2, "minecraft:glass_pane")
    BUILD.set(CX, 2, Z1, "minecraft:spruce_door[facing=south,half=lower,hinge=left]")
    BUILD.set(CX, 3, Z1, "minecraft:spruce_door[facing=south,half=upper,hinge=left]")
    BUILD.line((CX, 2, Z0 + 1), (CX, TOP, Z0 + 1), "minecraft:ladder[facing=south]")

    # parapet platform, one block out on upside-down stair corbels
    P0X, P1X, P0Z, P1Z = X0 - 1, X1 + 1, Z0 - 1, Z1 + 1
    BUILD.box((P0X, TOP + 1, P0Z), (P1X, TOP + 1, P1Z), "minecraft:polished_andesite")
    BUILD.set(CX, TOP + 1, Z0 + 1, "minecraft:spruce_trapdoor[facing=south,half=top]")
    BUILD.line(
        (X0, TOP, P0Z), (X1, TOP, P0Z), "minecraft:stone_brick_stairs[facing=south,half=top]"
    )
    BUILD.line(
        (X0, TOP, P1Z), (X1, TOP, P1Z), "minecraft:stone_brick_stairs[facing=north,half=top]"
    )
    BUILD.line((P0X, TOP, Z0), (P0X, TOP, Z1), "minecraft:stone_brick_stairs[facing=east,half=top]")
    BUILD.line((P1X, TOP, Z0), (P1X, TOP, Z1), "minecraft:stone_brick_stairs[facing=west,half=top]")
    BUILD.walls(
        (P0X, TOP + 2, P0Z),
        (P1X, TOP + 2, P1Z),
        lambda x, y, z: (
            "minecraft:stone_bricks" if (x + z) % 2 == 0 else "minecraft:stone_brick_wall"
        ),
    )
    for x, z in ((P0X, P0Z), (P1X, P0Z), (P0X, P1Z), (P1X, P1Z)):
        BUILD.set(x, TOP + 3, z, LANTERN)

    # turret roof on four posts, finial
    for x, z in ((X0, Z0), (X1, Z0), (X0, Z1), (X1, Z1)):
        BUILD.pillar((x, TOP + 2, z), 2, "minecraft:spruce_fence")
    BUILD.roof_hip(
        (X0 - 1, TOP + 4, Z0 - 1), (X1 + 1, TOP + 4, Z1 + 1), ROOF, hip="minecraft:deepslate_tiles"
    )
    BUILD.pillar((CX, TOP + 8, CZ), 2, "minecraft:deepslate_tile_wall")
    BUILD.set(CX, TOP + 10, CZ, "minecraft:lightning_rod[facing=up]")
