"""Waystone variant — Sunken Reliquary Ruin (5x5x5, Argon edition)."""

import mcbuilder as mb

SB = "minecraft:stone_bricks"
MSB = "minecraft:mossy_stone_bricks"
CSB = "minecraft:cracked_stone_bricks"
CHSB = "minecraft:chiseled_stone_bricks"
COB = "minecraft:cobblestone"
MCOB = "minecraft:mossy_cobblestone"
AND = "minecraft:polished_andesite"
LODE = "minecraft:lodestone"
WAYSTONE = "lostqol:waystone"

VIEWS = ["iso", "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top"]

BUILD = mb.Build(seed=404, views=VIEWS)

with BUILD:
    # ------------------------------------------------------------------
    # y=0 : 5x5 Weathered ruin foundation on terrain (nothing below y=0)
    # ------------------------------------------------------------------
    for x in range(5):
        for z in range(5):
            if (x, z) == (2, 2):
                b = CHSB
            elif x == 2 or z == 2:
                b = AND  # Smooth worn processional cross
            elif (x, z) in ((0, 0), (0, 4)):
                b = MCOB
            elif (x, z) in ((4, 0), (4, 4)):
                b = COB
            elif (x * 3 + z * 5) % 3 == 0:
                b = MSB
            elif (x + z) % 2 == 0:
                b = CSB
            else:
                b = SB
            BUILD.set(x, 0, z, b)

    # ------------------------------------------------------------------
    # y=1 : Stepped plinth, 4 cardinal entrance steps & corner posts
    # ------------------------------------------------------------------
    # Inner 3x3 sanctum platform
    BUILD.set(2, 1, 2, AND)
    BUILD.set(2, 1, 1, SB)
    BUILD.set(2, 1, 3, MSB)
    BUILD.set(1, 1, 2, MSB)
    BUILD.set(3, 1, 2, CSB)

    for ix, iz in ((1, 1), (3, 1), (1, 3), (3, 3)):
        BUILD.set(ix, 1, iz, SB)

    # 4 outer cardinal entrance stairs (Step 1 ascending inward from terrain)
    BUILD.set(2, 1, 0, "minecraft:stone_brick_stairs[facing=south,half=bottom]")
    BUILD.set(2, 1, 4, "minecraft:mossy_stone_brick_stairs[facing=north,half=bottom]")
    BUILD.set(0, 1, 2, "minecraft:mossy_stone_brick_stairs[facing=east,half=bottom]")
    BUILD.set(4, 1, 2, "minecraft:stone_brick_stairs[facing=west,half=bottom]")

    # 4 outer corner lantern pedestals
    for cx, cz in ((0, 0), (4, 0), (0, 4), (4, 4)):
        BUILD.set(cx, 1, cz, CHSB)

    # 8 outer recessed curb slabs linking the corner pedestals to the stairs
    for wx, wz, wblock in (
        (1, 0, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (0, 1, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (3, 0, "minecraft:stone_brick_slab[type=bottom]"),
        (4, 1, "minecraft:stone_brick_slab[type=bottom]"),
        (1, 4, "minecraft:stone_brick_slab[type=bottom]"),
        (0, 3, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (3, 4, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (4, 3, "minecraft:stone_brick_slab[type=bottom]"),
    ):
        BUILD.set(wx, 1, wz, wblock)

    # ------------------------------------------------------------------
    # y=2 : Lodestone pedestal, upper altar stairs, pillars & lanterns
    # ------------------------------------------------------------------
    BUILD.set(2, 2, 2, LODE)

    # 4 upper altar stairs (Step 2 ascending inward to the lodestone pedestal)
    BUILD.set(2, 2, 1, "minecraft:polished_andesite_stairs[facing=south,half=bottom]")
    BUILD.set(2, 2, 3, "minecraft:polished_andesite_stairs[facing=north,half=bottom]")
    BUILD.set(1, 2, 2, "minecraft:polished_andesite_stairs[facing=east,half=bottom]")
    BUILD.set(3, 2, 2, "minecraft:polished_andesite_stairs[facing=west,half=bottom]")

    # 4 inner sanctum pillars (lower shaft)
    BUILD.set(1, 2, 1, MSB)
    BUILD.set(3, 2, 1, SB)
    BUILD.set(1, 2, 3, CSB)
    BUILD.set(3, 2, 3, MSB)

    # 4 standing lanterns on the outer corner pedestals
    for cx, cz in ((0, 0), (4, 0), (0, 4), (4, 4)):
        BUILD.set(cx, 2, cz, "minecraft:lantern[hanging=false]")

    # ------------------------------------------------------------------
    # y=3 : lostqol:waystone at (2,3,2), pillar capitals & hanging lanterns
    # ------------------------------------------------------------------
    BUILD.set(2, 3, 2, WAYSTONE)

    # 4 inner sanctum pillar capitals (chiseled stone bricks)
    for ix, iz in ((1, 1), (3, 1), (1, 3), (3, 3)):
        BUILD.set(ix, 3, iz, CHSB)

    # 4 hanging lanterns suspended under the cardinal portal keystones
    for lx, lz in ((2, 0), (2, 4), (0, 2), (4, 2)):
        BUILD.set(lx, 3, lz, "minecraft:lantern[hanging=true]")

    # ------------------------------------------------------------------
    # y=4 : Stepped overhanging canopy (notched corners + pyramid crown)
    # ------------------------------------------------------------------
    # Center keystone crown
    BUILD.set(2, 4, 2, LODE)

    # Inner 3x3 stepped pyramid cap: cardinal stairs + mitered outer-corner stairs
    BUILD.set(2, 4, 1, "minecraft:stone_brick_stairs[facing=south,half=bottom]")
    BUILD.set(2, 4, 3, "minecraft:mossy_stone_brick_stairs[facing=north,half=bottom]")
    BUILD.set(1, 4, 2, "minecraft:mossy_stone_brick_stairs[facing=east,half=bottom]")
    BUILD.set(3, 4, 2, "minecraft:stone_brick_stairs[facing=west,half=bottom]")

    BUILD.set(1, 4, 1, "minecraft:mossy_stone_brick_stairs[facing=south,half=bottom,shape=outer_left]")
    BUILD.set(3, 4, 1, "minecraft:stone_brick_stairs[facing=south,half=bottom,shape=outer_right]")
    BUILD.set(1, 4, 3, "minecraft:stone_brick_stairs[facing=north,half=bottom,shape=outer_right]")
    BUILD.set(3, 4, 3, "minecraft:mossy_stone_brick_stairs[facing=north,half=bottom,shape=outer_left]")

    # 4 cardinal portal arch keystones (supporting the hanging lanterns at y=3)
    BUILD.set(2, 4, 0, "minecraft:polished_andesite_slab[type=bottom]")
    BUILD.set(2, 4, 4, "minecraft:polished_andesite_slab[type=bottom]")
    BUILD.set(0, 4, 2, "minecraft:polished_andesite_slab[type=bottom]")
    BUILD.set(4, 4, 2, "minecraft:polished_andesite_slab[type=bottom]")

    # 8 outer overhanging eave slabs (corners left notched open over the y=2 lanterns)
    for ex, ez, eblock in (
        (1, 0, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (0, 1, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (3, 0, "minecraft:stone_brick_slab[type=bottom]"),
        (4, 1, "minecraft:stone_brick_slab[type=bottom]"),
        (1, 4, "minecraft:stone_brick_slab[type=bottom]"),
        (0, 3, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (3, 4, "minecraft:mossy_stone_brick_slab[type=bottom]"),
        (4, 3, "minecraft:stone_brick_slab[type=bottom]"),
    ):
        BUILD.set(ex, 4, ez, eblock)
