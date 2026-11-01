"""Tudor house: stone ground floor, jettied timber upper floor, cross gable,
dormers, outside chimney. Paste on flat ground; the foundation is y = 0..1.

Footprint 20 x 15, 22 tall. Coordinates are kept from the original layout
(the front door faces south at z = -2).
"""

import mcbuilder as mb

from common import (
    BRICK,
    FOUNDATION,
    HANGING_LANTERN,
    PLANK_FLOOR,
    PLASTER,
    ROOF,
    ROOF_EAVE,
    STONE_BASE,
    TIMBER,
    VERGE,
    dormer,
    even_posts,
    gable_infill,
    lantern_post,
    window,
)

BUILD = mb.Build(seed=1207, views="iso;az200_el025;az020_el030")

X0, X1, Z0, Z1 = -10, 2, -14, -6  # ground-floor wall planes
BAY_X0, BAY_X1, BAY_Z1 = -7, -1, -2  # front bay (porch) walls, front at z = -2
UX0, UX1, UZ0, UZ1 = X0 - 1, X1 + 1, Z0 - 1, Z1 + 1  # upper floor, 1 block jetty


def timber_frame(x0, x1, z0, z1, *, skip=None):
    """Upper-floor walls y = 7..11: posts, sill (7), plate (11), plaster."""
    xs, zs = even_posts(x0, x1), even_posts(z0, z1)
    sides = {
        "north": [(x, z0) for x in range(x0, x1 + 1)],
        "south": [(x, z1) for x in range(x0, x1 + 1)],
        "west": [(x0, z) for z in range(z0, z1 + 1)],
        "east": [(x1, z) for z in range(z0, z1 + 1)],
    }
    for side, cells in sides.items():
        if side == skip:
            continue
        run = "x" if side in ("north", "south") else "z"
        for x, z in cells:
            if (x in xs) if run == "x" else (z in zs):
                BUILD.pillar((x, 7, z), 5, f"{TIMBER}[axis=y]")
            else:
                BUILD.set(x, 7, z, f"{TIMBER}[axis={run}]")
                BUILD.box((x, 8, z), (x, 10, z), PLASTER)
                BUILD.set(x, 11, z, f"{TIMBER}[axis={run}]")
    return xs, zs


with BUILD:
    # -- ground floor ----------------------------------------------------------
    BUILD.box((X0 - 1, 0, Z0 - 1), (X1 + 1, 1, Z1 + 1), FOUNDATION)
    BUILD.box((BAY_X0 - 1, 0, Z1), (BAY_X1 + 1, 1, BAY_Z1 + 1), FOUNDATION)
    BUILD.box((X0, 1, Z0), (X1, 1, Z1), PLANK_FLOOR)
    BUILD.box((BAY_X0, 1, Z1 + 1), (BAY_X1, 1, BAY_Z1), PLANK_FLOOR)
    BUILD.walls((X0, 2, Z0), (X1, 5, Z1), STONE_BASE)
    BUILD.walls((BAY_X0, 2, Z1), (BAY_X1, 5, BAY_Z1), STONE_BASE)
    BUILD.carve((BAY_X0 + 1, 2, Z1), (BAY_X1 - 1, 5, Z1))  # bay opens into the hall
    for x, z in ((X0, Z0), (X1, Z0), (X0, Z1), (X1, Z1), (BAY_X0, BAY_Z1), (BAY_X1, BAY_Z1)):
        BUILD.pillar((x, 2, z), 4, "minecraft:polished_andesite")  # quoins

    # -- jetty: upper deck 1 block out, log joist ends, stair corbels ------------
    BUILD.box((UX0, 6, UZ0), (UX1, 6, UZ1), PLANK_FLOOR)
    BUILD.box((BAY_X0 - 1, 6, Z1 + 1), (BAY_X1 + 1, 6, BAY_Z1 + 1), PLANK_FLOOR)
    BUILD.line((UX0, 6, UZ0), (UX1, 6, UZ0), f"{TIMBER}[axis=x]")
    BUILD.line((UX0, 6, UZ0), (UX0, 6, UZ1), f"{TIMBER}[axis=z]")
    BUILD.line((UX1, 6, UZ0), (UX1, 6, UZ1), f"{TIMBER}[axis=z]")
    for x in range(X0, X1 + 1, 2):
        BUILD.set(x, 5, Z0 - 1, "minecraft:dark_oak_stairs[facing=south,half=top]")
    for z in range(Z0, Z1 + 1, 2):
        BUILD.set(X0 - 1, 5, z, "minecraft:dark_oak_stairs[facing=east,half=top]")
        BUILD.set(X1 + 1, 5, z, "minecraft:dark_oak_stairs[facing=west,half=top]")

    # -- upper floor --------------------------------------------------------------
    xs, zs = timber_frame(UX0, UX1, UZ0, UZ1)
    timber_frame(BAY_X0 - 1, BAY_X1 + 1, Z1 + 1, BAY_Z1 + 1, skip="north")
    BUILD.carve((BAY_X0, 7, UZ1), (BAY_X1, 10, UZ1))
    for i, (a, b) in enumerate(zip(xs, xs[1:])):
        if i % 2 == 0:
            window(BUILD, (a + b) // 2, 8, UZ0, "north")
        else:
            BUILD.line((a + 1, 9, UZ0), (b - 1, 9, UZ0), f"{TIMBER}[axis=x]")  # mid rail
    for a, b in zip(zs, zs[1:]):
        window(BUILD, UX0, 8, (a + b) // 2, "west")
        window(BUILD, UX1, 8, (a + b) // 2, "east")
    window(BUILD, -4, 8, BAY_Z1 + 1, "south")
    for x in (UX0 + 2, UX1 - 2):
        window(BUILD, x, 8, UZ1, "south")

    # -- ground-floor windows and the front door -----------------------------------
    for x in (-8, -4, 0):
        window(BUILD, x, 3, Z0, "north", flower_box=False)
    for z in (-12, -8):
        window(BUILD, X0, 3, z, "west", flower_box=False)
    window(BUILD, X1, 3, -12, "east", flower_box=False)
    window(BUILD, -9, 3, Z1, "south")
    window(BUILD, 1, 3, Z1, "south")
    BUILD.set(-4, 2, BAY_Z1, "minecraft:spruce_door[facing=north,half=lower,hinge=left]")
    BUILD.set(-4, 3, BAY_Z1, "minecraft:spruce_door[facing=north,half=upper,hinge=left]")
    BUILD.box(
        (-5, 1, BAY_Z1 + 1),
        (-3, 1, BAY_Z1 + 1),
        "minecraft:stone_brick_stairs[facing=north,half=bottom]",
    )
    BUILD.set(-4, 5, BAY_Z1 + 1, HANGING_LANTERN)
    for x in (-6, -2):
        lantern_post(BUILD, x, 1, BAY_Z1 + 2, height=1, post="minecraft:cobblestone_wall")

    # -- roofs: cross gable over the bay, then the main roof ------------------------
    BUILD.roof_gable(
        (BAY_X0 - 2, 12, -9),
        (BAY_X1 + 2, 12, BAY_Z1 + 2),
        ROOF,
        ridge="z",
        verge=VERGE,
        eave=ROOF_EAVE,
    )
    gable_infill(BUILD, BAY_Z1 + 1, "z", 12, BAY_X0 - 2, BAY_X1 + 2, window_at=(13, -4))
    BUILD.roof_gable(
        (UX0 - 1, 12, UZ0 - 1), (UX1 + 1, 12, UZ1 + 1), ROOF, ridge="x", verge=VERGE, eave=ROOF_EAVE
    )
    for x in (-9, -1):
        dormer(BUILD, x, UZ0 - 1, 12)
    for plane in (UX0, UX1):
        gable_infill(BUILD, plane, "x", 12, UZ0 - 1, UZ1 + 1, window_at=(14, (UZ0 + UZ1) // 2))
    BUILD.line((UX0 - 1, 19, -10), (UX1 + 1, 19, -10), "minecraft:deepslate_tile_slab[type=bottom]")

    # -- chimney on the east gable --------------------------------------------------
    BUILD.box((UX1 + 2, 0, -11), (UX1 + 3, 20, -9), BRICK)
    BUILD.box((UX1 + 1, 12, -11), (UX1 + 1, 13, -9), BRICK)
    BUILD.box((UX1 + 2, 21, -11), (UX1 + 3, 21, -9), "minecraft:stone_brick_slab[type=bottom]")
    BUILD.set(UX1 + 3, 21, -10, "minecraft:campfire[lit=true]")

    # hedge on the front foundation ledge
    for x in range(X0 - 1, X1 + 2):
        if BUILD.get(x, 2, Z1 + 1) is None and not BAY_X0 - 1 <= x <= BAY_X1 + 1:
            BUILD.set(x, 2, Z1 + 1, "minecraft:oak_leaves[persistent=true]")

    # -- interior ------------------------------------------------------------------
    for z, block in zip(
        range(-13, -9),
        (
            "minecraft:smoker[facing=west,lit=true]",
            "minecraft:barrel[facing=up]",
            "minecraft:crafting_table",
            "minecraft:furnace[facing=west]",
        ),
    ):
        BUILD.set(1, 2, z, block)
    BUILD.box((-9, 2, -13), (-9, 2, -12), "minecraft:chest[facing=east]")
    BUILD.box((-9, 2, -11), (-9, 3, -11), "minecraft:barrel[facing=east]")
    BUILD.box((-5, 2, -10), (-3, 2, -10), "minecraft:spruce_slab[type=top]")
    BUILD.box((-5, 2, -11), (-3, 2, -11), "minecraft:spruce_stairs[facing=north]")
    BUILD.box((-5, 2, -9), (-3, 2, -9), "minecraft:spruce_stairs[facing=south]")
    BUILD.set(-4, 3, -10, "minecraft:candle[candles=3,lit=true]")
    BUILD.set(-4, 5, -10, HANGING_LANTERN)
    BUILD.set(-4, 5, -4, HANGING_LANTERN)
    BUILD.line((-9, 2, -7), (-9, 6, -7), "minecraft:ladder[facing=east]")
    for x in (-8, -6):
        BUILD.set(x, 7, -13, "minecraft:blue_bed[facing=north,part=head]")
        BUILD.set(x, 7, -12, "minecraft:blue_bed[facing=north,part=foot]")
    BUILD.box((-3, 7, -14), (1, 8, -14), "minecraft:bookshelf")
    BUILD.set(-1, 7, -12, "minecraft:enchanting_table")
    BUILD.set(1, 7, -9, "minecraft:lectern[facing=west]")
    BUILD.set(-4, 11, -10, HANGING_LANTERN)
