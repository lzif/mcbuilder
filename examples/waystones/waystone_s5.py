"""Waystone variant 5 — Classic Ruin (5x5x5).

A compact 5x5x5 waystone using the classic_ruin palette:
stone bricks, mossy stone bricks, cracked stone bricks,
chiseled stone bricks, polished andesite, iron chains, lanterns.

Layout:
  y=4 : hanging lantern at (2,4,2)
  y=3 : lostqol:waystone at (2,3,2)
  y=2 : pedestal (center)
  y=1 : stepped base (3x3 center + inward-facing stair edges)
  y=0 : floor (5x5 with material variation, sits ON TOP of terrain, dyMin=0)

No common.py imported — this script is 5x5x5, not 7x7x7.
"""

import mcbuilder as mb

# Classic ruin palette
STONE_BRICK = "minecraft:stone_bricks"
MOSSY_SB = "minecraft:mossy_stone_bricks"
CRACKED_SB = "minecraft:cracked_stone_bricks"
CHISELED_SB = "minecraft:chiseled_stone_bricks"
POLISHED_AND = "minecraft:polished_andesite"
IRON_CHAIN = "minecraft:iron_chain[axis=y]"
LANTERN = "minecraft:lantern"
WAYSTONE = "lostqol:waystone"

VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=201, views=VIEWS)


def _secondary_maybe(x, z):
    """Return secondary block ~30% of the time, otherwise stone bricks."""
    if (x * 7 + z * 11 + 201) % 10 < 3:  # ~30%
        choices = [MOSSY_SB, CRACKED_SB, CHISELED_SB]
        return choices[(x * 5 + z * 7) % 3]
    return STONE_BRICK


def _main():
    with BUILD:
        # Floor y=0: 5x5 with material variation and trim
        for x in range(5):
            for z in range(5):
                block = _secondary_maybe(x, z)
                # Corner accents
                if (x, z) in ((0, 0), (4, 0), (0, 4), (4, 4)):
                    block = CHISELED_SB
                # Border trim
                elif x in (0, 4) or z in (0, 4):
                    block = CRACKED_SB
                # Center cross in andesite
                elif (x, z) == (2, 2):
                    block = POLISHED_AND
                elif x == 2 and z in (1, 3):
                    block = POLISHED_AND
                elif z == 2 and x in (1, 3):
                    block = POLISHED_AND
                # Mossy edge accents
                elif x == 1 and z == 0:
                    block = MOSSY_SB
                elif x == 3 and z == 0:
                    block = MOSSY_SB
                elif z == 1 and x == 0:
                    block = MOSSY_SB
                elif z == 3 and x == 0:
                    block = MOSSY_SB
                else:
                    block = STONE_BRICK
                BUILD.set(x, 0, z, block)

        # Stepped base y=1: 3x3 center + stair edges facing inward
        # 3x3 center full stone bricks
        for x in range(1, 4):
            for z in range(1, 4):
                BUILD.set(x, 1, z, STONE_BRICK)
        # Inward-facing stair edges
        # z=1 row (facing south)
        for x in range(1, 4):
            BUILD.set(x, 1, 1, f"minecraft:stone_brick_stairs[facing=south,half=bottom]")
        # z=3 row (facing north)
        for x in range(1, 4):
            BUILD.set(x, 1, 3, f"minecraft:stone_brick_stairs[facing=north,half=bottom]")
        # x=1 column (facing east)
        for z in range(1, 4):
            BUILD.set(1, 1, z, f"minecraft:stone_brick_stairs[facing=east,half=bottom]")
        # x=3 column (facing west)
        for z in range(1, 4):
            BUILD.set(3, 1, z, f"minecraft:stone_brick_stairs[facing=west,half=bottom]")
        # Corner accents on the step
        BUILD.set(1, 1, 1, CHISELED_SB)  # front-left
        BUILD.set(3, 1, 1, CHISELED_SB)  # front-right
        BUILD.set(1, 1, 3, CHISELED_SB)  # back-left
        BUILD.set(3, 1, 3, CHISELED_SB)  # back-right

        # Pedestal y=2: center column with variation
        BUILD.set(2, 2, 2, POLISHED_AND)
        BUILD.set(3, 2, 2, CHISELED_SB)  # X+
        BUILD.set(1, 2, 2, CHISELED_SB)  # X-
        BUILD.set(2, 2, 3, MOSSY_SB)      # Z+
        BUILD.set(2, 2, 1, CRACKED_SB)    # Z-
        BUILD.set(3, 2, 3, MOSSY_SB)      # diagonal
        BUILD.set(3, 2, 1, CRACKED_SB)    # diagonal
        BUILD.set(1, 2, 3, CRACKED_SB)    # diagonal
        BUILD.set(1, 2, 1, MOSSY_SB)      # diagonal

        # lostqol:waystone at (2,3,2)
        BUILD.set(2, 3, 2, WAYSTONE)

        # Hanging lantern at (2,4,2)
        BUILD.set(2, 4, 2, LANTERN)

        # Iron chains around the pedestal area
        for cx, cz in ((1, 1), (1, 3), (3, 1), (3, 3)):
            for y in range(3, 5):
                BUILD.set(cx, y, cz, IRON_CHAIN)


_main()