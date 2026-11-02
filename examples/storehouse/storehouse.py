"""Storehouse: a two-story medieval storage building, no terrain.

Ground floor in mixed stone between spruce posts, jettied plaster upper
floor, steep thick deepslate roof with dark oak trim, a front wall dormer
with a hoist for the loft, a loading dock and a woodshed lean-to.
Front (big doors) faces south. Paste on flat ground; the plinth is y = 0.
"""

import mcbuilder as mb

BUILD = mb.Build(seed=31, views="az200_el025;az330_el030;az135_el035")

# -- palette --------------------------------------------------------------------
STONE = mb.patches(
    [
        ("minecraft:stone_bricks", 4),
        ("minecraft:cobblestone", 2),
        ("minecraft:mossy_stone_bricks", 1),
        ("minecraft:cracked_stone_bricks", 1),
        ("minecraft:andesite", 1),
    ],
    scale=1.5,
    salt="stone",
)
PLINTH = mb.patches(
    [
        ("minecraft:cobbled_deepslate", 2),
        ("minecraft:cobblestone", 2),
        "minecraft:deepslate_bricks",
    ],
    scale=1.5,
    salt="plinth",
)
PLASTER = mb.patches([("minecraft:calcite", 5), "minecraft:diorite"], scale=2, salt="plaster")
ROOF = mb.patches(
    [
        ("minecraft:deepslate_brick_stairs", 3),
        ("minecraft:cobbled_deepslate_stairs", 2),
        "minecraft:deepslate_tile_stairs",
    ],
    scale=2,
    salt="roof",
)
POST = "minecraft:stripped_spruce_log[axis=y]"
TRIM = "minecraft:dark_oak"  # + _stairs / _planks / _slab / _log ...
LANTERN = "minecraft:lantern"
HANGING = "minecraft:lantern[hanging=true]"

# -- dimensions -----------------------------------------------------------------
# Three depth planes per facade: posts (outer), ground infill (1 in),
# and the jettied upper floor whose posts sit 1 out from the ground posts.
X0, X1, Z0, Z1 = 0, 15, 0, 10  # ground-floor post planes
GROUND_POSTS_X = (0, 4, 11, 15)
GROUND_POSTS_Z = (0, 5, 10)
UX0, UX1, UZ0, UZ1 = X0 - 1, X1 + 1, Z0 - 1, Z1 + 1  # upper-floor post planes
UPPER_POSTS_X = (UX0, 4, 11, UX1)
EAVE_Y = 11
DORMER_X0, DORMER_X1 = 3, 12  # front wall dormer roof footprint (x)

OUT = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
INWARD = {"north": "south", "south": "north", "west": "east", "east": "west"}


def stair(name, facing, top=False):
    return f"minecraft:{name}_stairs[facing={facing},half={'top' if top else 'bottom'}]"


def thicken(geo, under_edge):
    """Make a stair roof read as thick: a full block under every stair.

    Edge cells (eave row and gable verges) get dark oak planks, a two-block
    fascia like the references; the rest gets the stair's own full block.
    """
    (x0, y0, z0), (x1, _, z1) = geo.bounds()
    for x, y, z, block in geo.cells():
        if BUILD.get(x, y - 1, z) is not None:
            continue
        if under_edge(x, y, z, x0, x1, z0, z1, y0):
            BUILD.set(x, y - 1, z, f"{TRIM}_planks")
        else:
            full = block.split("[")[0].replace("_stairs", "")
            full = {
                "minecraft:deepslate_brick": "minecraft:deepslate_bricks",
                "minecraft:deepslate_tile": "minecraft:deepslate_tiles",
                "minecraft:dark_oak": "minecraft:dark_oak_planks",
            }.get(full, full)
            BUILD.set(x, y - 1, z, full)


def facade_cells(side, plane_lo, plane_hi, lo, hi):
    """(x, z) cells along one facade between lo..hi on the given plane."""
    if side in ("north", "south"):
        z = plane_lo if side == "north" else plane_hi
        return [(x, z) for x in range(lo, hi + 1)]
    x = plane_lo if side == "west" else plane_hi
    return [(x, z) for z in range(lo, hi + 1)]


def window(
    x,
    y,
    z,
    face,
    *,
    width=1,
    height=2,
    glass="minecraft:glass_pane",
    shutters="dark_oak",
    lintel=None,
):
    """Window set into an infill plane, framed in the plane in front of it."""
    ox, oz = OUT[face]
    sx, sz = (1, 0) if face in ("north", "south") else (0, 1)
    for i in range(width):
        BUILD.pillar((x + i * sx, y, z + i * sz), height, glass)
    for i in (-1, width):
        BUILD.pillar(
            (x + i * sx + ox, y, z + i * sz + oz),
            height,
            f"minecraft:{shutters}_trapdoor[facing={face},half=bottom,open=true]",
        )
    if lintel:
        for i in range(width):
            BUILD.set(x + i * sx, y + height, z + i * sz, stair(lintel, INWARD[face], top=True))


def flower_box(x, y, z, face, width=2, plants=("minecraft:sweet_berry_bush[age=2]",)):
    """Planter in front of a window: dirt + plants, trapdoor front, corbel under."""
    ox, oz = OUT[face]
    sx, sz = (1, 0) if face in ("north", "south") else (0, 1)
    for i in range(width):
        cx, cz = x + i * sx, z + i * sz
        BUILD.set(cx, y, cz, "minecraft:rooted_dirt")
        BUILD.set(cx, y + 1, cz, plants[i % len(plants)])
        BUILD.set(
            cx + ox, y, cz + oz, f"minecraft:spruce_trapdoor[facing={face},half=bottom,open=true]"
        )
        BUILD.set(cx, y - 1, cz, stair("spruce", INWARD[face], top=True))


def gable_infill(plane, y0, lo, hi, *, kingpost=True, window_at=None):
    """Timber-and-plaster triangle under a ridge-x gable, in plane x = plane."""
    mid = (lo + hi) // 2
    k = 0
    while lo + k + 1 <= hi - k - 1:
        a, b = lo + k + 1, hi - k - 1
        for z in range(a, b + 1):
            if kingpost and z == mid:
                block = POST
            elif z in (a, b):
                block = f"{TRIM}_log[axis=z]"
            else:
                block = PLASTER
            BUILD.set(plane, y0 + k, z, block)
        k += 1
    if window_at:
        wy, *zs = window_at
        for z in zs:
            BUILD.set(plane, wy, z, "minecraft:glass_pane")


with BUILD:
    # =========================================================================
    # plinth, floor, loading dock
    # =========================================================================
    BUILD.box((X0 - 1, 0, Z0 - 1), (X1 + 1, 0, Z1 + 1), PLINTH)
    BUILD.box((X0 + 2, 0, Z0 + 2), (X1 - 2, 0, Z1 - 2), "minecraft:spruce_planks")
    BUILD.box((3, 0, Z1 + 2), (12, 0, Z1 + 3), PLINTH)  # dock
    BUILD.line((5, 0, Z1 + 4), (10, 0, Z1 + 4), stair("stone_brick", "north"))  # steps up

    # =========================================================================
    # ground floor: posts on the outer plane, stone infill 1 block in
    # =========================================================================
    for x in GROUND_POSTS_X:
        for z in (Z0, Z1):
            BUILD.pillar((x, 1, z), 4, POST)
    for z in GROUND_POSTS_Z:
        for x in (X0, X1):
            BUILD.pillar((x, 1, z), 4, POST)
    BUILD.walls((X0 + 1, 1, Z0 + 1), (X1 - 1, 4, Z1 - 1), STONE)
    # floor beam on the post plane
    BUILD.line((X0, 5, Z0), (X1, 5, Z0), "minecraft:stripped_spruce_log[axis=x]")
    BUILD.line((X0, 5, Z1), (X1, 5, Z1), "minecraft:stripped_spruce_log[axis=x]")
    BUILD.line((X0, 5, Z0 + 1), (X0, 5, Z1 - 1), "minecraft:stripped_spruce_log[axis=z]")
    BUILD.line((X1, 5, Z0 + 1), (X1, 5, Z1 - 1), "minecraft:stripped_spruce_log[axis=z]")
    # sloped stone skirt in the recesses between posts
    for side, (plo, phi) in {"north": (Z0, Z1), "south": (Z0, Z1)}.items():
        for x, z in facade_cells(side, plo, phi, X0 + 1, X1 - 1):
            if x not in GROUND_POSTS_X:
                BUILD.set(x, 1, z, stair("stone_brick", INWARD[side]))
    for side in ("west", "east"):
        for x, z in facade_cells(side, X0, X1, Z0 + 1, Z1 - 1):
            if z not in GROUND_POSTS_Z:
                BUILD.set(x, 1, z, stair("stone_brick", INWARD[side]))

    # barred storage windows with stone lintels
    for x in (2, 13):
        window(
            x,
            2,
            Z0 + 1,
            "north",
            glass="minecraft:iron_bars",
            shutters="spruce",
            lintel="stone_brick",
        )
    window(
        2, 2, Z1 - 1, "south", glass="minecraft:iron_bars", shutters="spruce", lintel="stone_brick"
    )
    window(
        13, 2, Z1 - 1, "south", glass="minecraft:iron_bars", shutters="spruce", lintel="stone_brick"
    )
    for z in (2, 8):
        window(
            X0 + 1,
            2,
            z,
            "west",
            glass="minecraft:iron_bars",
            shutters="spruce",
            lintel="stone_brick",
        )

    # big double doors, framed in dark oak, lanterns on fences beside them
    for x in (6, 9):
        BUILD.pillar((x, 1, Z1), 4, "minecraft:stripped_dark_oak_log[axis=y]")
    BUILD.box((7, 1, Z1 - 1), (8, 4, Z1 - 1), "minecraft:air")
    BUILD.set(7, 1, Z1 - 1, "minecraft:spruce_door[facing=north,half=lower,hinge=left]")
    BUILD.set(7, 2, Z1 - 1, "minecraft:spruce_door[facing=north,half=upper,hinge=left]")
    BUILD.set(8, 1, Z1 - 1, "minecraft:spruce_door[facing=north,half=lower,hinge=right]")
    BUILD.set(8, 2, Z1 - 1, "minecraft:spruce_door[facing=north,half=upper,hinge=right]")
    BUILD.box((7, 3, Z1 - 1), (8, 4, Z1 - 1), "minecraft:spruce_planks")
    BUILD.line((7, 4, Z1), (8, 4, Z1), stair("dark_oak", "north", top=True))
    for x in (5, 10):
        BUILD.pillar((x, 1, Z1), 3, f"{TRIM}_fence")
        BUILD.set(x, 4, Z1, HANGING)

    # =========================================================================
    # jetty: upper deck 1 block out, alternating corbel band underneath
    # =========================================================================
    BUILD.box((UX0, 6, UZ0), (UX1, 6, UZ1), f"{TRIM}_planks")
    for i, (x, z) in enumerate(facade_cells("north", UZ0, UZ1, UX0, UX1)):
        BUILD.set(
            x, 5, z, stair("dark_oak", "south", top=True) if i % 2 else f"{TRIM}_slab[type=top]"
        )
    for i, (x, z) in enumerate(facade_cells("south", UZ0, UZ1, UX0, UX1)):
        if not 5 <= x <= 10:  # doorway stays open under the dormer platform
            BUILD.set(
                x, 5, z, stair("dark_oak", "north", top=True) if i % 2 else f"{TRIM}_slab[type=top]"
            )
    for i, (x, z) in enumerate(facade_cells("west", UX0, UX1, UZ0 + 1, UZ1 - 1)):
        BUILD.set(
            x, 5, z, stair("dark_oak", "east", top=True) if i % 2 else f"{TRIM}_slab[type=top]"
        )
    for i, (x, z) in enumerate(facade_cells("east", UX0, UX1, UZ0 + 1, UZ1 - 1)):
        BUILD.set(
            x, 5, z, stair("dark_oak", "west", top=True) if i % 2 else f"{TRIM}_slab[type=top]"
        )

    # =========================================================================
    # upper floor: posts and plaster flush on the jettied plane; depth comes
    # from shutters, flower boxes and the corbel band, not from a recess
    # =========================================================================
    for x in UPPER_POSTS_X:
        for z in (UZ0, UZ1):
            BUILD.pillar((x, 6, z), 5, POST)
    for z in (UZ0, 5, UZ1):
        for x in (UX0, UX1):
            BUILD.pillar((x, 6, z), 5, POST)
    BUILD.walls((UX0, 7, UZ0), (UX1, 9, UZ1), PLASTER)
    # sill (y=6) and plate (y=10) beams on the post plane
    for y in (6, 10):
        for z in (UZ0, UZ1):
            for x in range(UX0 + 1, UX1):
                if x not in UPPER_POSTS_X:
                    BUILD.set(x, y, z, "minecraft:stripped_spruce_log[axis=x]")
        for x in (UX0, UX1):
            for z in range(UZ0 + 1, UZ1):
                if z != 5:
                    BUILD.set(x, y, z, "minecraft:stripped_spruce_log[axis=z]")
    # rivets on the posts
    for x in UPPER_POSTS_X:
        BUILD.set(x, 9, UZ1 + 1, f"{TRIM}_button[face=wall,facing=south]")
        BUILD.set(x, 9, UZ0 - 1, f"{TRIM}_button[face=wall,facing=north]")

    # upper windows: shutters on the post plane, top-slab lintel, two flower boxes
    for x in (1, 12):
        window(x, 7, UZ0, "north", width=2)
        window(x, 7, UZ1, "south", width=2)
    flower_box(1, 6, UZ1 + 1, "south")
    flower_box(12, 6, UZ1 + 1, "south", plants=("minecraft:azure_bluet", "minecraft:poppy"))
    for x in (6, 9):
        window(x, 7, UZ0, "north")
    for z in (2, 8):
        window(UX0, 7, z, "west")
        window(UX1, 7, z, "east")

    # loft door in the dormer bay, with a gated landing for loading
    BUILD.box((7, 7, UZ1), (8, 9, UZ1), "minecraft:air")
    BUILD.line((7, 7, UZ1), (8, 7, UZ1), f"{TRIM}_fence_gate[facing=south]")
    for x in (6, 9):
        BUILD.pillar(
            (x, 7, UZ1 + 1), 3, "minecraft:spruce_trapdoor[facing=south,half=bottom,open=true]"
        )
    BUILD.box((6, 5, UZ1), (9, 5, UZ1), stair("dark_oak", "north", top=True))

    # =========================================================================
    # roofs: front wall dormer, then the main roof around it
    # =========================================================================
    main = mb.shapes.roof_gable(
        (UX0 - 1, EAVE_Y, UZ0 - 1),
        (UX1 + 1, EAVE_Y, UZ1 + 1),
        ROOF,
        ridge="x",
        verge=f"{TRIM}_stairs",
        eave=f"{TRIM}_stairs",
        seed=BUILD.seed,
    )
    dormer = mb.shapes.roof_gable(
        (DORMER_X0, EAVE_Y, 6),
        (DORMER_X1, EAVE_Y, UZ1 + 1),
        ROOF,
        ridge="z",
        verge=f"{TRIM}_stairs",
        eave=f"{TRIM}_stairs",
        seed=BUILD.seed,
    )

    def dormer_top(x):
        return EAVE_Y + min(x - DORMER_X0, DORMER_X1 - x)

    def main_top(z):  # height of the main roof's south slope at z
        return EAVE_Y + (UZ1 + 1 - z)

    keep_main = mb.Geometry()
    for x, y, z, b in main.cells():
        inside_dormer = DORMER_X0 <= x <= DORMER_X1 and z >= 6 and y < dormer_top(x)
        if not inside_dormer:
            keep_main.set(x, y, z, b)
    keep_dormer = mb.Geometry()
    for x, y, z, b in dormer.cells():
        if y > main_top(z) or z > UZ1:
            keep_dormer.set(x, y, z, b)
    placed_main = BUILD.place(keep_main)
    placed_dormer = BUILD.place(keep_dormer)

    def main_edge(x, y, z, x0, x1, z0, z1, y0):
        return x in (x0, x1) or y == y0

    thicken(placed_main, main_edge)
    thicken(placed_dormer, lambda x, y, z, *_: x in (DORMER_X0, DORMER_X1) or y == EAVE_Y)

    # gable ends: timber + plaster, small window
    for plane in (UX0, UX1):
        gable_infill(plane, EAVE_Y, UZ0 - 1, UZ1 + 1, window_at=(13, 4, 6))
    # dormer gable on the front plane, loft opening at its foot
    k = 0
    while DORMER_X0 + k + 1 <= DORMER_X1 - k - 1:
        for x in range(DORMER_X0 + k + 1, DORMER_X1 - k):
            edge = x in (DORMER_X0 + k + 1, DORMER_X1 - k - 1)
            BUILD.set(x, EAVE_Y + k, UZ1, f"{TRIM}_log[axis=x]" if edge else PLASTER)
        k += 1
    BUILD.box((7, EAVE_Y, UZ1), (8, EAVE_Y + 1, UZ1), POST)

    # ridge cap and crossed beam "horns" at both gable peaks, with hanging lanterns
    ridge_z = (UZ0 - 1 + UZ1 + 1) // 2
    ridge_y = EAVE_Y + (UZ1 + 1 - (UZ0 - 1)) // 2
    BUILD.line(
        (UX0 - 1, ridge_y + 1, ridge_z),
        (UX1 + 1, ridge_y + 1, ridge_z),
        f"{TRIM}_slab[type=bottom]",
    )
    for x, out in ((UX0 - 1, -1), (UX1 + 1, 1)):
        for k in (1, 2):
            BUILD.set(x, ridge_y + k, ridge_z - k, stair("dark_oak", "north"))
            BUILD.set(x, ridge_y + k, ridge_z + k, stair("dark_oak", "south"))
        BUILD.set(x, ridge_y + 1, ridge_z, f"{TRIM}_planks")
        BUILD.set(x + out, ridge_y, ridge_z, f"{TRIM}_log[axis=x]")
        BUILD.line(
            (x + out, ridge_y - 1, ridge_z),
            (x + out, ridge_y - 3, ridge_z),
            "minecraft:iron_chain[axis=y]",
        )
        BUILD.set(x + out, ridge_y - 4, ridge_z, HANGING)
    # ridge vent cupola: louvred box with its own little hip roof
    cy = ridge_y + 2
    for x in (6, 9):
        for z in (ridge_z - 1, ridge_z + 1):
            BUILD.pillar((x, cy, z), 2, POST)
    for x in (7, 8):
        for z, face in ((ridge_z - 1, "north"), (ridge_z + 1, "south")):
            BUILD.pillar(
                (x, cy, z), 2, f"minecraft:spruce_trapdoor[facing={face},half=bottom,open=true]"
            )
    BUILD.box((7, cy - 1, ridge_z), (8, cy - 1, ridge_z), f"{TRIM}_planks")
    BUILD.box((7, cy, ridge_z), (8, cy + 1, ridge_z), "minecraft:air")
    BUILD.roof_hip((5, cy + 2, ridge_z - 2), (10, cy + 2, ridge_z + 2), ROOF, hip=f"{TRIM}_planks")
    BUILD.set(7, cy + 4, ridge_z, "minecraft:lightning_rod[facing=up]")

    # eave-corner lanterns hanging under the fascia
    for x in (UX0 - 1, UX1 + 1):
        for z in (UZ0 - 1, UZ1 + 1):
            BUILD.set(x, EAVE_Y - 2, z, HANGING)

    # hoist: beam out of the dormer gable, chain, hanging barrel
    hoist_y = EAVE_Y + 3
    BUILD.line(
        (7, hoist_y, UZ1 - 1), (7, hoist_y, UZ1 + 3), "minecraft:stripped_dark_oak_log[axis=z]"
    )
    BUILD.line((7, hoist_y - 1, UZ1 + 3), (7, hoist_y - 4, UZ1 + 3), "minecraft:iron_chain[axis=y]")
    BUILD.set(7, hoist_y - 5, UZ1 + 3, "minecraft:barrel[facing=up]")

    # =========================================================================
    # woodshed lean-to on the east side
    # =========================================================================
    SX = X1 + 5
    BUILD.box((X1 + 1, 0, 1), (SX, 0, 9), PLINTH)
    for z in (1, 5, 9):
        BUILD.pillar((SX, 1, z), 3, POST)
    BUILD.line((SX, 4, 0), (SX, 4, 10), stair("dark_oak", "west"))
    BUILD.line((SX - 1, 5, 0), (SX - 1, 5, 10), stair("dark_oak", "west"))
    BUILD.box((X1 + 2, 5, 0), (SX - 2, 5, 10), f"{TRIM}_slab[type=bottom]")
    BUILD.box(
        (X1 + 2, 1, 2),
        (SX - 1, 2, 4),
        [
            ("minecraft:oak_log[axis=z]", 2),
            "minecraft:spruce_log[axis=z]",
            "minecraft:birch_log[axis=z]",
        ],
    )
    BUILD.box((X1 + 2, 3, 2), (SX - 2, 3, 4), "minecraft:oak_log[axis=z]")
    BUILD.box((X1 + 2, 1, 6), (X1 + 3, 2, 8), "minecraft:barrel[facing=up]")
    BUILD.set(SX - 1, 1, 7, "minecraft:hay_block[axis=x]")
    BUILD.set(SX - 1, 1, 8, "minecraft:composter[level=4]")
    BUILD.set(SX, 4, 5, HANGING.replace("hanging=true", "hanging=false"))

    # =========================================================================
    # dock props: the storage touch outside
    # =========================================================================
    BUILD.box((3, 1, Z1 + 2), (4, 2, Z1 + 2), "minecraft:barrel[facing=up]")
    BUILD.set(3, 1, Z1 + 3, "minecraft:barrel[facing=south]")
    BUILD.set(5, 1, Z1 + 2, "minecraft:composter[level=7]")
    BUILD.box((11, 1, Z1 + 2), (12, 1, Z1 + 3), "minecraft:hay_block[axis=x]")
    BUILD.set(12, 2, Z1 + 2, "minecraft:hay_block[axis=z]")
    BUILD.set(10, 1, Z1 + 2, "minecraft:barrel[facing=east]")
    for x in (2, 13):
        BUILD.pillar((x, 1, Z1 + 3), 2, f"{TRIM}_fence")
        BUILD.set(x, 3, Z1 + 3, LANTERN)

    # =========================================================================
    # interior: shelves, barrels, chests below; hay loft above
    # =========================================================================
    BUILD.line((3, 2, Z0 + 2), (12, 2, Z0 + 2), "minecraft:spruce_shelf[facing=south]")
    BUILD.line((3, 3, Z0 + 2), (12, 3, Z0 + 2), "minecraft:spruce_shelf[facing=south]")
    BUILD.box((X0 + 2, 1, 3), (X0 + 2, 3, 7), "minecraft:barrel[facing=east]")
    BUILD.box((X1 - 2, 1, 3), (X1 - 2, 1, 6), "minecraft:chest[facing=west]")
    BUILD.line((X1 - 2, 1, 7), (X1 - 2, 6, 7), "minecraft:ladder[facing=west]")
    BUILD.set(7, 4, 5, HANGING)
    BUILD.box((1, 7, 1), (4, 8, 3), "minecraft:hay_block[axis=y]")
    BUILD.box((11, 7, 1), (14, 7, 2), "minecraft:barrel[facing=up]")
    BUILD.set(7, 10, 5, HANGING)
