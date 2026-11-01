"""Riverside homestead — full survival base (mcbuilder probe, agent-authored).

Zones (ground top surface y=0, +X east, +Z south):
  - main house: two-story Tudor, stone ground floor, jettied timber upper
    floor, cross-gabled deepslate roof, exterior brick chimney
  - barn + lean-to forge (workshop), hay-loft hoist
  - watchtower on the NW hill, crenellated parapet + turret roof
  - farm (two hedged plots, water channels, scarecrow), animal pen
  - courtyard with a roofed well
  - stream on the east edge with an arched bridge and a fishing dock
  - palisade with lantern posts, south gate, patchy paths, trees

Technique checklist (docs/build-patterns.md): material noise on every big
surface, skeleton-first timber frame, story bands, jetty + corbels,
cross gable, chimney accent, crenellated base, hedges, lantern rhythm,
props, siting on a stream + hill.
"""

import math

import mcbuilder as mb
from mcbuilder.blocks import resolve_material

BUILD = mb.Build(seed=1207, views=["iso", "az135_el025", "az225_el030",
                                    "az315_el025", "top"])

# --- palette --------------------------------------------------------------
STONE_BASE = [("minecraft:stone_bricks", 5), ("minecraft:cracked_stone_bricks", 1),
              ("minecraft:mossy_stone_bricks", 2), ("minecraft:andesite", 1),
              ("minecraft:cobblestone", 1)]
FOUNDATION = [("minecraft:cobblestone", 4), ("minecraft:mossy_cobblestone", 2),
              ("minecraft:stone", 1)]
PLASTER = [("minecraft:calcite", 5), ("minecraft:smooth_quartz", 1),
           ("minecraft:white_concrete_powder", 1)]
BARN_WALL = [("minecraft:spruce_planks", 5), ("minecraft:stripped_spruce_wood", 1),
             ("minecraft:dark_oak_planks", 1)]
PLANK_FLOOR = [("minecraft:spruce_planks", 3), ("minecraft:oak_planks", 1)]
BRICK = [("minecraft:bricks", 5), ("minecraft:mud_bricks", 1),
         ("minecraft:stone_bricks", 1)]
PATH = [("minecraft:dirt_path", 8), ("minecraft:coarse_dirt", 1),
        ("minecraft:gravel", 1)]
PLAZA = [("minecraft:cobblestone", 3), ("minecraft:gravel", 2),
         ("minecraft:stone_bricks", 2), ("minecraft:mossy_cobblestone", 1),
         ("minecraft:dirt_path", 2)]
TIMBER = "minecraft:dark_oak_log"
ROOF = "minecraft:deepslate_tile_stairs"
LANTERN = "minecraft:lantern"
HANG = "minecraft:lantern[hanging=true]"

def put(x, y, z, spec):
    """BUILD.set that accepts a material spec (set() only takes a string)."""
    BUILD.set(x, y, z, resolve_material(spec, x, y, z, BUILD.seed))


# --- terrain --------------------------------------------------------------
X0, X1, Z0, Z1 = -36, 40, -32, 30
HILL_C, HILL_TOP, HILL_PLATEAU = (-22, -20), 4, 6
occupied: set[tuple[int, int]] = set()  # columns scatter must avoid


_lat: dict = {}


def vnoise(x, z, scale, salt):
    """Smooth value noise in [0,1): clustered patches, not per-cell speckle."""
    fx, fz = x / scale, z / scale
    ix, iz = math.floor(fx), math.floor(fz)
    tx, tz = fx - ix, fz - iz
    tx, tz = tx * tx * (3 - 2 * tx), tz * tz * (3 - 2 * tz)

    def h(a, b):
        k = (salt, a, b)
        if k not in _lat:
            _lat[k] = BUILD.rng(f"{salt}:{a},{b}").random()
        return _lat[k]
    top = h(ix, iz) * (1 - tx) + h(ix + 1, iz) * tx
    bot = h(ix, iz + 1) * (1 - tx) + h(ix + 1, iz + 1) * tx
    return top * (1 - tz) + bot * tz


def in_plate(x, z):
    """Rounded-rectangle diorama plate."""
    cx, cz, hx, hz, r = 2, -1, 38, 31, 8
    dx, dz = max(0, abs(x - cx) - (hx - r)), max(0, abs(z - cz) - (hz - r))
    return dx * dx + dz * dz <= r * r


def stream_x(z):
    return 29 + round(2 * math.sin(z / 6))


def ground(x, z):
    """Top surface y of the terrain column."""
    d = math.hypot(x - HILL_C[0], z - HILL_C[1]) - 5 * (vnoise(x, z, 7, "hill") - 0.5)
    hill = HILL_TOP if d <= HILL_PLATEAU else max(0, HILL_TOP - math.ceil((d - HILL_PLATEAU) / 3.5))
    off = abs(x - stream_x(z))
    if off <= 2:
        return -3          # stream bed
    if off == 3:
        return -1          # sandy bank
    return hill


def mark(x0, z0, x1, z1):
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for z in range(min(z0, z1), max(z0, z1) + 1):
            occupied.add((x, z))


def terrain():
    for x in range(X0, X1 + 1):
        for z in range(Z0, Z1 + 1):
            if not in_plate(x, z):
                continue
            top = ground(x, z)
            for y in range(-5, top):
                BUILD.set(x, y, z, "minecraft:stone" if y <= -4 else "minecraft:dirt")
            off = abs(x - stream_x(z))
            if off <= 2:
                put(x, top, z, ["minecraft:gravel", "minecraft:sand",
                                      ("minecraft:clay", 0.5)])
                BUILD.box((x, -2, z), (x, -1, z), "minecraft:water")
            elif off == 3:
                put(x, top, z, [("minecraft:sand", 3), "minecraft:gravel",
                                      ("minecraft:grass_block", 1)])
            else:
                n = vnoise(x, z, 5, "soil")
                BUILD.set(x, top, z, "minecraft:coarse_dirt" if n > 0.86 else
                          "minecraft:moss_block" if n < 0.1 else "minecraft:grass_block")


def ground_set(x, z, block):
    """Replace the terrain top cell (paths, farmland)."""
    put(x, ground(x, z), z, block)


# --- generic pieces -------------------------------------------------------

def even_posts(a, b, gap=3.5):
    n = max(1, round((b - a) / gap))
    return sorted({a + round((b - a) * i / n) for i in range(n + 1)})


def window(x, y, z, face, *, tall=2, shutters=True, box=True):
    """Glass-pane window in a wall plane; face = outward direction."""
    pane_axis = "x" if face in ("north", "south") else "z"
    for dy in range(tall):
        BUILD.set(x, y + dy, z, "minecraft:glass_pane")
    ox, oz = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}[face]
    sx, sz = (1, 0) if pane_axis == "x" else (0, 1)
    if shutters:
        for s in (-1, 1):
            for dy in range(tall):
                BUILD.set(x + ox + s * sx, y + dy, z + oz + s * sz,
                          f"minecraft:spruce_trapdoor[facing={face},half=bottom,open=true]")
    if box:  # flower box: greenery sitting on a top-half trapdoor ledge
        BUILD.set(x + ox, y - 1, z + oz, "minecraft:flowering_azalea_leaves[persistent=true]")
        if BUILD.get(x + ox, y - 2, z + oz) is None:
            BUILD.set(x + ox, y - 2, z + oz,
                      f"minecraft:spruce_trapdoor[facing={face},half=top,open=false]")


def tree(x, z, kind, h, r=2):
    g = ground(x, z)
    log = f"minecraft:{kind}_log[axis=y]"
    leaves = f"minecraft:{kind}_leaves[persistent=true]"
    rng = BUILD.rng(f"tree{x},{z}")
    occupied.add((x, z))
    if kind == "spruce":
        for i, rad in enumerate([3, 3, 2, 2, 1, 1, 0]):
            y = g + h - 4 + i
            for dx in range(-rad, rad + 1):
                for dz in range(-rad, rad + 1):
                    if abs(dx) + abs(dz) <= rad + (i % 2) and (dx or dz or i >= 4):
                        BUILD.set(x + dx, y, z + dz, leaves)
        BUILD.line((x, g + 1, z), (x, g + h + 1, z), log)
        BUILD.set(x, g + h + 3, z, leaves)
        return
    BUILD.line((x, g + 1, z), (x, g + h, z), log)
    cy = g + h
    for dx in range(-r, r + 1):
        for dy in range(-1, r + 1):
            for dz in range(-r, r + 1):
                d = dx * dx + dy * dy * 1.6 + dz * dz
                if d <= r * r + 1 and not (dx == 0 and dz == 0 and dy <= 0):
                    if d > (r - 0.5) ** 2 and rng.random() < 0.25:
                        continue  # ragged edge
                    BUILD.set(x + dx, cy + dy, z + dz, leaves)


def gable_infill(plane, axis, y0, lo, hi, *, kingpost=True, window_at=None,
                 fill=None, edge_block=TIMBER):
    """Fill the triangle under a gable roof: plane = x (axis='x' gable end
    lies in x=plane, spans z lo..hi) or z. Timber border + plaster."""
    k = 0
    while lo + k + 1 <= hi - k - 1:
        y = y0 + k
        a, b = lo + k + 1, hi - k - 1
        for w in range(a, b + 1):
            edge = w in (a, b)
            mid = (lo + hi) // 2
            blk = (f"{edge_block}[axis=y]" if (kingpost and w == mid) else
                   (f"{edge_block}[axis={'z' if axis == 'x' else 'x'}]" if edge else (fill or PLASTER)))
            pos = (plane, y, w) if axis == "x" else (w, y, plane)
            put(*pos, blk)
        k += 1
    if window_at:
        wy, ww = window_at
        for w in (ww - 1, ww + 1):
            pos = (plane, wy, w) if axis == "x" else (w, wy, plane)
            BUILD.set(*pos, "minecraft:glass_pane")


def retrim(geo, *, verge=None, rows=None, block_from, block_to):
    """Re-material parts of a placed roof: the gable-end (verge) columns
    and/or chosen slope rows, keeping each stair's facing/half."""
    (x0, y0, z0), (x1, _, z1) = geo.bounds()
    for x, y, z, b in geo.cells():
        hit = (verge == "x" and x in (x0, x1)) or (verge == "z" and z in (z0, z1))
        hit = hit or (rows is not None and (y - y0) in rows)
        if hit and BUILD.get(x, y, z) == b:
            BUILD.set(x, y, z, b.replace(block_from, block_to))


def dormer(x0, roof_eave_z, eave_y):
    """3-wide gabled dormer on the NORTH slope of a ridge='x' roof.

    Front wall 3 tall sits where the main roof is 2 rows up; its own little
    gable roof (wood verge for contrast) runs back to the main ridge.
    """
    fz, fy = roof_eave_z + 2, eave_y + 2
    for x in range(x0, x0 + 3):
        for y in range(fy, fy + 3):
            if x == x0 + 1 and y < fy + 2:
                BUILD.set(x, y, fz, "minecraft:glass_pane")
            elif x != x0 + 1:
                BUILD.set(x, y, fz, f"{TIMBER}[axis=y]")
            else:
                BUILD.set(x, y, fz, f"{TIMBER}[axis=x]")
    for x in (x0, x0 + 2):
        for k in range(1, 3):
            for y in range(fy + k, fy + 3):
                put(x, y, fz + k, PLASTER)
    roof = BUILD.roof_gable((x0 - 1, fy + 3, fz - 1), (x0 + 3, fy + 3, fz + 4), ROOF, ridge="z")
    retrim(roof, verge="z", block_from="deepslate_tile", block_to="dark_oak")
    put(x0 + 1, fy + 3, fz, PLASTER)
    BUILD.set(x0 + 1, fy + 3, fz - 1, "minecraft:dark_oak_stairs[facing=south,half=bottom]")


def lantern_post(x, z, h=2, post="minecraft:spruce_fence"):
    g = ground(x, z)
    BUILD.line((x, g + 1, z), (x, g + h, z), post)
    BUILD.set(x, g + h + 1, z, LANTERN)
    occupied.add((x, z))


# --- main house -----------------------------------------------------------
HX0, HX1, HZ0, HZ1 = -10, 2, -14, -6   # ground-floor wall planes
BAY = (-7, -1, -5, -2)                  # front bay x0,x1,z0(back),z1(front)


def house():
    mark(HX0 - 2, HZ0 - 2, HX1 + 4, HZ1 + 2)
    mark(BAY[0] - 1, BAY[3], BAY[1] + 1, BAY[3] + 2)
    # foundation (1 wider), crenellated top edge
    BUILD.box((HX0 - 1, 0, HZ0 - 1), (HX1 + 1, 1, HZ1 + 1), FOUNDATION)
    BUILD.box((BAY[0] - 1, 0, BAY[2]), (BAY[1] + 1, 1, BAY[3] + 1), FOUNDATION)
    for x in range(HX0 - 1, HX1 + 2, 2):
        for z in (HZ0 - 1,):
            BUILD.set(x, 2, z, "minecraft:cobblestone_wall")
    BUILD.box((HX0, 1, HZ0), (HX1, 1, HZ1), PLANK_FLOOR)
    BUILD.box((BAY[0], 1, BAY[2]), (BAY[1], 1, BAY[3]), PLANK_FLOOR)
    # ground floor: stone walls y2..5 (main + bay), open between them
    BUILD.walls((HX0, 2, HZ0), (HX1, 5, HZ1), STONE_BASE)
    BUILD.walls((BAY[0], 2, BAY[2] - 1), (BAY[1], 5, BAY[3]), STONE_BASE)
    BUILD.carve((BAY[0] + 1, 2, HZ1), (BAY[1] - 1, 5, BAY[2]))
    # stone quoins: corners in plain stone bricks, full height
    for x, z in ((HX0, HZ0), (HX1, HZ0), (HX0, HZ1), (HX1, HZ1),
                 (BAY[0], BAY[3]), (BAY[1], BAY[3])):
        BUILD.line((x, 2, z), (x, 5, z), "minecraft:polished_andesite")
    # upper floor deck, jettied 1 block out on every side
    UX0, UX1, UZ0, UZ1 = HX0 - 1, HX1 + 1, HZ0 - 1, HZ1 + 1
    BUILD.box((UX0, 6, UZ0), (UX1, 6, UZ1), PLANK_FLOOR)
    BUILD.box((BAY[0] - 1, 6, BAY[2]), (BAY[1] + 1, 6, BAY[3] + 1), PLANK_FLOOR)
    # joist ends: dark log band around the deck edge
    for x in range(UX0, UX1 + 1):
        BUILD.set(x, 6, UZ0, f"{TIMBER}[axis=x]")
    for z in range(UZ0, UZ1 + 1):
        BUILD.set(UX0, 6, z, f"{TIMBER}[axis=z]")
        BUILD.set(UX1, 6, z, f"{TIMBER}[axis=z]")
    # corbels: upside-down stairs under the jetty, back against the wall
    for x in range(HX0, HX1 + 1, 2):
        BUILD.set(x, 5, HZ0 - 1, "minecraft:dark_oak_stairs[facing=south,half=top]")
    for z in range(HZ0, HZ1 + 1, 2):
        BUILD.set(HX0 - 1, 5, z, "minecraft:dark_oak_stairs[facing=east,half=top]")
        BUILD.set(HX1 + 1, 5, z, "minecraft:dark_oak_stairs[facing=west,half=top]")
    # upper floor timber frame y7..11 (sill 7, plate 11)
    def frame(x0, x1, z0, z1, skip_side=None):
        xs, zs = even_posts(x0, x1), even_posts(z0, z1)
        sides = {"north": [(x, z0) for x in range(x0, x1 + 1)],
                 "south": [(x, z1) for x in range(x0, x1 + 1)],
                 "west": [(x0, z) for z in range(z0, z1 + 1)],
                 "east": [(x1, z) for z in range(z0, z1 + 1)]}
        for side, cells in sides.items():
            if side == skip_side:
                continue
            horiz = "x" if side in ("north", "south") else "z"
            for x, z in cells:
                post = (x in xs) if horiz == "x" else (z in zs)
                for y in range(7, 12):
                    if post:
                        BUILD.set(x, y, z, f"{TIMBER}[axis=y]")
                    elif y in (7, 11):
                        BUILD.set(x, y, z, f"{TIMBER}[axis={horiz}]")
                    else:
                        put(x, y, z, PLASTER)
        return xs, zs
    xs, zs = frame(UX0, UX1, UZ0, UZ1)
    frame(BAY[0] - 1, BAY[1] + 1, BAY[2], BAY[3] + 1, skip_side="north")
    BUILD.carve((BAY[0], 7, UZ1), (BAY[1], 10, UZ1))  # bay opens into house
    # upper windows: middle of alternate panels; X-braces in the others
    for i, (a, b) in enumerate(zip(xs, xs[1:])):
        m = (a + b) // 2
        if i % 2 == 0:
            window(m, 8, UZ0, "north", shutters=True, box=True)
        else:
            for k in range(1, b - a):  # close studding: mid-rail + short studs
                BUILD.set(a + k, 9, UZ0, f"{TIMBER}[axis=x]")
    for a, b in zip(zs, zs[1:]):
        m = (a + b) // 2
        window(UX0, 8, m, "west")
        window(UX1, 8, m, "east")
    window(-4, 8, BAY[3] + 1, "south")
    for x in (UX0 + 2, UX1 - 2):
        window(x, 8, UZ1, "south")
    # ground-floor windows
    for x in (-8, -4, 0):
        window(x, 3, HZ0, "north", box=False)
    for z in (-12, -8):
        window(HX0, 3, z, "west", box=False)
    window(HX1, 3, -12, "east", box=False)
    window(-9, 3, HZ1, "south")
    window(1, 3, HZ1, "south")
    # door + steps + flanking lanterns
    BUILD.set(-4, 2, BAY[3], "minecraft:spruce_door[facing=north,half=lower,hinge=left]")
    BUILD.set(-4, 3, BAY[3], "minecraft:spruce_door[facing=north,half=upper,hinge=left]")
    BUILD.box((-5, 1, BAY[3] + 1), (-3, 1, BAY[3] + 1),
              "minecraft:stone_brick_stairs[facing=north,half=bottom]")
    BUILD.set(-4, 5, BAY[3] + 1, HANG)
    for x in (-6, -2):
        lantern_post(x, BAY[3] + 2, h=1, post="minecraft:cobblestone_wall")
    # roofs: cross gable over the bay first, main roof second
    bay_roof = BUILD.roof_gable((BAY[0] - 2, 12, -9), (BAY[1] + 2, 12, BAY[3] + 2), ROOF, ridge="z")
    gable_infill(BAY[3] + 1, "z", 12, BAY[0] - 2, BAY[1] + 2, window_at=(13, -4))
    main_roof = BUILD.roof_gable((UX0 - 1, 12, UZ0 - 1), (UX1 + 1, 12, UZ1 + 1), ROOF, ridge="x")
    # two-tone: wooden bargeboards on the gable ends, brick-grey eave course
    retrim(main_roof, verge="x", block_from="deepslate_tile", block_to="dark_oak")
    retrim(main_roof, rows={0}, block_from="deepslate_tile", block_to="deepslate_brick")
    retrim(bay_roof, verge="z", block_from="deepslate_tile", block_to="dark_oak")
    retrim(bay_roof, rows={0}, block_from="deepslate_tile", block_to="deepslate_brick")
    for dx in (-9, -1):
        dormer(dx, UZ0 - 1, 12)
    for plane in (UX0, UX1):
        gable_infill(plane, "x", 12, UZ0 - 1, UZ1 + 1, window_at=(14, (UZ0 + UZ1) // 2))
    # ridge cap
    for x in range(UX0 - 1, UX1 + 2):
        BUILD.set(x, 19, (UZ0 + UZ1) // 2, "minecraft:deepslate_tile_slab[type=bottom]")
    # exterior chimney (east), campfire smoke on top
    cx0, cx1 = UX1 + 2, UX1 + 3
    BUILD.box((cx0, 0, -11), (cx1, 20, -9), BRICK)
    BUILD.box((cx0, 21, -11), (cx1, 21, -9), "minecraft:stone_brick_slab[type=bottom]")
    BUILD.set(cx1, 21, -10, "minecraft:campfire[lit=true]")
    BUILD.box((cx0 - 1, 12, -11), (cx0 - 1, 13, -9), BRICK)  # seal against roof
    mark(cx0, -11, cx1, -9)
    # hedge on the foundation ledge where there's no window box
    for x in range(HX0 - 1, HX1 + 2):
        if BUILD.get(x, 2, HZ1 + 1) is None and not (BAY[0] - 1 <= x <= BAY[1] + 1):
            BUILD.set(x, 2, HZ1 + 1, "minecraft:oak_leaves[persistent=true]")
    house_interior()


def house_interior():
    # ground floor: kitchen east, dining middle, storage west
    BUILD.set(1, 2, -13, "minecraft:smoker[facing=west,lit=true]")
    BUILD.set(1, 2, -12, "minecraft:barrel[facing=up]")
    BUILD.set(1, 2, -11, "minecraft:crafting_table")
    BUILD.set(1, 2, -10, "minecraft:furnace[facing=west]")
    for z in (-13, -12):
        BUILD.set(-9, 2, z, "minecraft:chest[facing=east]")
    BUILD.set(-9, 2, -11, "minecraft:barrel[facing=east]")
    BUILD.set(-9, 3, -11, "minecraft:barrel[facing=east]")
    for x in (-5, -4, -3):
        BUILD.set(x, 2, -10, "minecraft:spruce_slab[type=top]")
        BUILD.set(x, 2, -11, "minecraft:spruce_stairs[facing=north]")
        BUILD.set(x, 2, -9, "minecraft:spruce_stairs[facing=south]")
    BUILD.set(-4, 3, -10, "minecraft:candle[candles=3,lit=true]")
    BUILD.set(-4, 5, -10, HANG)
    BUILD.set(-4, 5, -4, HANG)
    BUILD.set(-7, 1, -10, "minecraft:red_carpet")
    # ladder up (west wall), hole in upper floor
    BUILD.line((-9, 2, -7), (-9, 6, -7), "minecraft:ladder[facing=east]")
    # upper floor: bedroom
    BUILD.set(-8, 7, -13, "minecraft:blue_bed[facing=north,part=head]")
    BUILD.set(-8, 7, -12, "minecraft:blue_bed[facing=north,part=foot]")
    BUILD.set(-6, 7, -13, "minecraft:blue_bed[facing=north,part=head]")
    BUILD.set(-6, 7, -12, "minecraft:blue_bed[facing=north,part=foot]")
    BUILD.box((-3, 7, -14), (1, 8, -14), "minecraft:bookshelf")
    BUILD.set(-1, 7, -12, "minecraft:enchanting_table")
    BUILD.set(1, 7, -9, "minecraft:lectern[facing=west]")
    BUILD.set(-4, 11, -10, HANG)


# --- barn + forge ---------------------------------------------------------
BX0, BX1, BZ0, BZ1 = 8, 18, -18, -10


def barn():
    mark(BX0 - 1, BZ0 - 1, BX1 + 6, BZ1 + 2)
    BUILD.box((BX0 - 1, 0, BZ0 - 1), (BX1 + 1, 1, BZ1 + 1), FOUNDATION)
    BUILD.box((BX0, 1, BZ0), (BX1, 1, BZ1), [("minecraft:spruce_planks", 2), "minecraft:coarse_dirt"])
    xs, zs = even_posts(BX0, BX1), even_posts(BZ0, BZ1)
    BUILD.walls((BX0, 2, BZ0), (BX1, 8, BZ1), BARN_WALL)
    for x in xs:
        for z in (BZ0, BZ1):
            BUILD.line((x, 2, z), (x, 8, z), "minecraft:stripped_spruce_log[axis=y]")
    for z in zs:
        for x in (BX0, BX1):
            BUILD.line((x, 2, z), (x, 8, z), "minecraft:stripped_spruce_log[axis=y]")
    for x in range(BX0, BX1 + 1):  # girt band
        for z in (BZ0, BZ1):
            if x not in xs:
                BUILD.set(x, 5, z, "minecraft:spruce_log[axis=x]")
    for z in range(BZ0, BZ1 + 1):
        for x in (BX0, BX1):
            if z not in zs:
                BUILD.set(x, 5, z, "minecraft:spruce_log[axis=z]")
    mid = (BX0 + BX1) // 2
    # big front door opening + frame
    BUILD.carve((mid - 1, 2, BZ1), (mid + 1, 5, BZ1))
    BUILD.line((mid - 2, 2, BZ1), (mid - 2, 6, BZ1), "minecraft:stripped_dark_oak_log[axis=y]")
    BUILD.line((mid + 2, 2, BZ1), (mid + 2, 6, BZ1), "minecraft:stripped_dark_oak_log[axis=y]")
    BUILD.line((mid - 2, 6, BZ1), (mid + 2, 6, BZ1), "minecraft:stripped_dark_oak_log[axis=x]")
    for x in (mid - 1, mid + 1):
        BUILD.set(x, 5, BZ1 + 1, HANG.replace("lantern", "lantern"))
    BUILD.set(mid - 1, 5, BZ1 + 1, "minecraft:air")
    BUILD.set(mid, 5, BZ1, "minecraft:air")
    BUILD.set(mid, 5, BZ1 + 1, "minecraft:air")
    for x in (mid - 3, mid + 3):
        BUILD.set(x, 4, BZ1 + 1, "minecraft:lantern[hanging=false]")
        BUILD.set(x, 3, BZ1 + 1, "minecraft:spruce_fence")
        BUILD.set(x, 2, BZ1 + 1, "minecraft:spruce_fence")
    for x in (BX0 + 2, BX1 - 2):
        window(x, 3, BZ1, "south", box=False)
    for z in (BZ0 + 2, BZ1 - 2):
        window(BX0, 3, z, "west", box=False)
    # roof (gable faces south), loft door + hoist beam
    barn_roof = BUILD.roof_gable((BX0 - 1, 9, BZ0 - 1), (BX1 + 1, 9, BZ1 + 1),
                                 "minecraft:dark_oak_stairs", ridge="z")
    retrim(barn_roof, rows={3}, block_from="dark_oak", block_to="spruce")
    retrim(barn_roof, verge="z", block_from="dark_oak", block_to="stripped_spruce" if False else "spruce")
    for plane in (BZ0, BZ1):
        gable_infill(plane, "z", 9, BX0 - 1, BX1 + 1, kingpost=False,
                     fill=[("minecraft:spruce_planks", 3), "minecraft:stripped_spruce_wood"],
                     edge_block="minecraft:stripped_spruce_log")
    # ridge cupola (vent) - one vertical accent on the long barn roof
    cz = (BZ0 + BZ1) // 2
    ry = 9 + 6
    for dx in (-1, 1):
        for dz in (-1, 1):
            BUILD.line((mid + dx, ry, cz + dz), (mid + dx, ry + 1, cz + dz), "minecraft:stripped_spruce_log[axis=y]")
    BUILD.box((mid, ry, cz - 1), (mid, ry + 1, cz + 1), "minecraft:spruce_trapdoor[facing=east,half=bottom,open=true]")
    BUILD.box((mid - 1, ry, cz), (mid + 1, ry + 1, cz), "minecraft:air")
    BUILD.set(mid, ry, cz, "minecraft:spruce_planks")
    hip_roof(mid - 2, mid + 2, cz - 2, cz + 2, ry + 2, "minecraft:dark_oak_stairs", "minecraft:dark_oak_planks")
    BUILD.set(mid, ry + 5, cz, "minecraft:lightning_rod[facing=up]")
    BUILD.box((mid - 1, 10, BZ1), (mid + 1, 11, BZ1), "minecraft:air")
    BUILD.set(mid, 10, BZ1, "minecraft:hay_block[axis=x]")
    BUILD.line((mid, 13, BZ1 - 1), (mid, 13, BZ1 + 2), "minecraft:stripped_spruce_log[axis=z]")
    BUILD.line((mid, 12, BZ1 + 2), (mid, 10, BZ1 + 2), "minecraft:iron_chain[axis=y]")
    BUILD.set(mid, 9, BZ1 + 2, "minecraft:barrel[facing=up]")
    # interior: hay stacks + storage
    BUILD.box((BX0 + 1, 2, BZ0 + 1), (BX0 + 3, 3, BZ0 + 2), "minecraft:hay_block[axis=y]")
    for z in range(BZ0 + 1, BZ1 - 1):
        BUILD.set(BX1 - 1, 2, z, "minecraft:chest[facing=west]" if z % 2 else "minecraft:barrel[facing=west]")
    # lean-to forge on the east side
    fx = BX1 + 5
    BUILD.box((BX1 + 1, 0, BZ0 + 1), (fx, 1, BZ1 - 1), FOUNDATION)
    BUILD.box((BX1 + 2, 1, BZ0 + 2), (fx - 1, 1, BZ1 - 2), [("minecraft:stone_bricks", 2), "minecraft:cobblestone", "minecraft:gravel"])
    for z in (BZ0 + 1, BZ1 - 1):
        BUILD.line((fx, 2, z), (fx, 3, z), "minecraft:stripped_spruce_log[axis=y]")
        BUILD.set(fx, 4, z, LANTERN)
    for i, x in enumerate(range(fx, BX1, -1)):
        BUILD.box((x, 4 + i, BZ0 + 1), (x, 4 + i, BZ1 - 1),
                  "minecraft:dark_oak_stairs[facing=west,half=bottom]")
    BUILD.set(fx, 4, BZ0 + 1, LANTERN)
    BUILD.set(fx, 4, BZ1 - 1, LANTERN)
    BUILD.set(fx, 5, BZ0 + 1, "minecraft:dark_oak_slab[type=bottom]")
    BUILD.set(fx, 5, BZ1 - 1, "minecraft:dark_oak_slab[type=bottom]")
    z = BZ0 + 2
    for blk in ["minecraft:blast_furnace[facing=east,lit=true]",
                "minecraft:anvil[facing=north]", "minecraft:grindstone[face=floor,facing=east]",
                "minecraft:smithing_table", "minecraft:lava_cauldron",
                "minecraft:stonecutter[facing=east]"]:
        BUILD.set(BX1 + 2, 2, z, blk)
        z += 1
    BUILD.set(fx - 1, 2, BZ0 + 2, "minecraft:barrel[facing=up]")
    BUILD.set(fx - 1, 3, BZ0 + 2, "minecraft:barrel[facing=up]")


# --- watchtower -----------------------------------------------------------

def tower():
    cx, cz = HILL_C
    x0, x1, z0, z1 = cx - 2, cx + 2, cz - 2, cz + 2
    g = HILL_TOP
    mark(x0 - 2, z0 - 2, x1 + 2, z1 + 2)
    BUILD.box((x0 - 1, g - 1, z0 - 1), (x1 + 1, g, z1 + 1), FOUNDATION)
    top = g + 16

    def aged(x, y, z):  # mossier low, cleaner high
        h = BUILD.rng(f"t{x},{y},{z}").random()
        moss = 0.45 * (1 - (y - g) / 16)
        if h < moss:
            return "minecraft:mossy_stone_bricks"
        if h < moss + 0.12:
            return "minecraft:cracked_stone_bricks"
        return "minecraft:stone_bricks"
    BUILD.walls((x0, g + 1, z0), (x1, top, z1), aged)
    BUILD.box((x0 + 1, g + 1, z0 + 1), (x1 - 1, g + 1, z1 - 1), "minecraft:spruce_planks")
    # belt course
    for x in range(x0 - 1, x1 + 2):
        for z in (z0 - 1, z1 + 1):
            BUILD.set(x, g + 8, z, "minecraft:stone_brick_slab[type=top]")
    for z in range(z0, z1 + 1):
        for x in (x0 - 1, x1 + 1):
            BUILD.set(x, g + 8, z, "minecraft:stone_brick_slab[type=top]")
    # arrow slits
    for y in (g + 5, g + 11):
        for x, z, f in ((cx, z0, "north"), (cx, z1, "south"), (x0, cz, "west"), (x1, cz, "east")):
            if not (f == "south" and y == g + 5):
                BUILD.box((x, y, z), (x, y + 1, z), "minecraft:glass_pane")
    # door
    BUILD.set(cx, g + 2, z1, "minecraft:spruce_door[facing=south,half=lower,hinge=left]")
    BUILD.set(cx, g + 3, z1, "minecraft:spruce_door[facing=south,half=upper,hinge=left]")
    BUILD.set(cx, g + 4, z1 + 1, HANG.replace("hanging=true", "hanging=false"))
    BUILD.set(cx, g + 4, z1 + 1, "minecraft:air")
    BUILD.line((cx, g + 2, z0 + 1), (cx, top, z0 + 1), "minecraft:ladder[facing=south]")
    # overhanging parapet platform on corbels
    p0x, p1x, p0z, p1z = x0 - 1, x1 + 1, z0 - 1, z1 + 1
    BUILD.box((p0x, top + 1, p0z), (p1x, top + 1, p1z), "minecraft:polished_andesite")
    BUILD.set(cx, top + 1, z0 + 1, "minecraft:spruce_trapdoor[facing=south,half=top]")
    for x in range(x0, x1 + 1):
        BUILD.set(x, top, z0 - 1, "minecraft:stone_brick_stairs[facing=south,half=top]")
        BUILD.set(x, top, z1 + 1, "minecraft:stone_brick_stairs[facing=north,half=top]")
    for z in range(z0, z1 + 1):
        BUILD.set(x0 - 1, top, z, "minecraft:stone_brick_stairs[facing=east,half=top]")
        BUILD.set(x1 + 1, top, z, "minecraft:stone_brick_stairs[facing=west,half=top]")
    for x in range(p0x, p1x + 1):
        for z in range(p0z, p1z + 1):
            if x in (p0x, p1x) or z in (p0z, p1z):
                merlon = (x + z) % 2 == 0
                BUILD.set(x, top + 2, z, "minecraft:stone_bricks" if merlon else "minecraft:stone_brick_wall")
    for x, z in ((p0x, p0z), (p1x, p0z), (p0x, p1z), (p1x, p1z)):
        BUILD.set(x, top + 3, z, LANTERN)
    # turret roof on four posts
    for x, z in ((x0, z0), (x1, z0), (x0, z1), (x1, z1)):
        BUILD.line((x, top + 2, z), (x, top + 3, z), "minecraft:spruce_fence")
    hip_roof(x0 - 1, x1 + 1, z0 - 1, z1 + 1, top + 4, ROOF, "minecraft:deepslate_tiles")
    BUILD.line((cx, top + 8, cz), (cx, top + 9, cz), "minecraft:deepslate_tile_wall")
    BUILD.set(cx, top + 10, cz, "minecraft:lightning_rod[facing=up]")


def hip_roof(x0, x1, z0, z1, y, stair, corner):
    k = 0
    while x0 + k <= x1 - k and z0 + k <= z1 - k:
        a, b, c, d = x0 + k, x1 - k, z0 + k, z1 - k
        if a == b or c == d:
            BUILD.box((a, y + k, c), (b, y + k, d), corner)
            break
        for x in range(a + 1, b):
            BUILD.set(x, y + k, c, f"{stair}[facing=south]")
            BUILD.set(x, y + k, d, f"{stair}[facing=north]")
        for z in range(c + 1, d):
            BUILD.set(a, y + k, z, f"{stair}[facing=east]")
            BUILD.set(b, y + k, z, f"{stair}[facing=west]")
        for x, z in ((a, c), (b, c), (a, d), (b, d)):
            BUILD.set(x, y + k, z, corner)
        k += 1


# --- farm, pen, well ------------------------------------------------------

def farm():
    fx0, fx1, fz0, fz1 = -28, -8, 6, 18
    mark(fx0, fz0, fx1, fz1)
    crops = [("minecraft:wheat", 7), ("minecraft:carrots", 7),
             ("minecraft:potatoes", 7), ("minecraft:beetroots", 3)]
    rng = BUILD.rng("farm")
    plots = [(fx0 + 1, -19), (-17, fx1 - 1)]
    for pi, (a, b) in enumerate(plots):
        for x in range(a, b + 1):
            for z in range(fz0 + 1, fz1):
                edge = x in (a, b) or z in (fz0 + 1, fz1 - 1)
                if edge:
                    BUILD.set(x, 0, z, f"minecraft:stripped_oak_log[axis={'z' if x in (a, b) else 'x'}]")
                    continue
                if z == (fz0 + fz1) // 2:
                    BUILD.set(x, 0, z, "minecraft:water")
                    continue
                BUILD.set(x, 0, z, "minecraft:farmland[moisture=7]")
                name, amax = crops[(pi * 2 + (z > (fz0 + fz1) // 2))]
                BUILD.set(x, 1, z, f"{name}[age={min(amax, rng.randint(amax - 3, amax + 1))}]")
    # middle strip: pumpkins & melons with stems
    for z in range(fz0 + 2, fz1 - 1):
        BUILD.set(-18, 0, z, "minecraft:farmland[moisture=7]")
        fruit = "pumpkin" if z < (fz0 + fz1) // 2 else "melon"
        if z % 2 == 0:
            BUILD.set(-18, 1, z, f"minecraft:{fruit}")
        else:
            BUILD.set(-18, 1, z, f"minecraft:attached_{fruit}_stem[facing=north]")
    # fence ring with gate (north), composters, scarecrow
    for x in range(fx0, fx1 + 1):
        for z in (fz0, fz1):
            BUILD.set(x, 1, z, "minecraft:oak_fence")
    for z in range(fz0, fz1 + 1):
        for x in (fx0, fx1):
            BUILD.set(x, 1, z, "minecraft:oak_fence")
    BUILD.set(-18, 1, fz0, "minecraft:oak_fence_gate[facing=north]")
    for x in (fx0, fx1):
        for z in (fz0, fz1):
            BUILD.set(x, 1, z, "minecraft:stripped_oak_log[axis=y]")
            BUILD.set(x, 2, z, LANTERN)
    BUILD.set(-20, 1, fz0 + 1, "minecraft:composter[level=5]")
    BUILD.set(-16, 1, fz0 + 1, "minecraft:composter[level=8]")
    sx, sz = -23, 10
    BUILD.set(sx, 1, sz, "minecraft:oak_fence")
    BUILD.set(sx, 2, sz, "minecraft:hay_block[axis=y]")
    BUILD.set(sx, 3, sz, "minecraft:carved_pumpkin[facing=north]")


def pen():
    px0, px1, pz0, pz1 = 6, 20, 7, 19
    mark(px0, pz0, px1, pz1)
    for x in range(px0, px1 + 1):
        for z in range(pz0, pz1 + 1):
            if x in (px0, px1) or z in (pz0, pz1):
                BUILD.set(x, 1, z, "minecraft:spruce_fence")
            else:
                ground_set(x, z, [("minecraft:grass_block", 3), "minecraft:coarse_dirt",
                                  ("minecraft:mud", 0.5)])
    for x in range(px0, px1 + 1, 7):
        for z in (pz0, pz1):
            BUILD.set(x, 1, z, "minecraft:stripped_spruce_log[axis=y]")
            BUILD.set(x, 2, z, LANTERN)
    BUILD.set(13, 1, pz0, "minecraft:spruce_fence_gate[facing=north]")
    BUILD.set(13, 1, pz0, "minecraft:spruce_fence_gate[facing=north]")
    # shelter lean-to along the south fence
    for x in (px0 + 1, px0 + 5):
        BUILD.line((x, 1, pz1 - 1), (x, 2, pz1 - 1), "minecraft:stripped_spruce_log[axis=y]")
    BUILD.box((px0 + 1, 3, pz1 - 3), (px0 + 5, 3, pz1 - 1), "minecraft:spruce_slab[type=bottom]")
    BUILD.box((px0 + 2, 1, pz1 - 2), (px0 + 3, 1, pz1 - 2), "minecraft:hay_block[axis=x]")
    BUILD.set(px0 + 2, 2, pz1 - 2, "minecraft:hay_block[axis=x]")
    BUILD.box((px1 - 4, 1, pz0 + 2), (px1 - 2, 1, pz0 + 2), "minecraft:water_cauldron[level=3]")
    BUILD.set(px1 - 2, 1, pz1 - 2, "minecraft:hay_block[axis=y]")


def well(cx, cz):
    mark(cx - 2, cz - 2, cx + 2, cz + 2)
    BUILD.box((cx - 1, -3, cz - 1), (cx + 1, 1, cz + 1), [("minecraft:mossy_cobblestone", 2), "minecraft:cobblestone"])
    BUILD.box((cx, -3, cz), (cx, 0, cz), "minecraft:water")
    BUILD.set(cx, 1, cz, "minecraft:air")
    for x, z in ((cx - 1, cz - 1), (cx + 1, cz - 1), (cx - 1, cz + 1), (cx + 1, cz + 1)):
        BUILD.line((x, 2, z), (x, 3, z), "minecraft:spruce_fence")
    hip_roof(cx - 1, cx + 1, cz - 1, cz + 1, 4, "minecraft:spruce_stairs", "minecraft:spruce_planks")
    BUILD.set(cx, 3, cz, "minecraft:iron_chain[axis=y]")
    BUILD.set(cx, 2, cz, HANG)


def orchard(x0, z0, cols=3, rows=3, step=5):
    """Fruit trees on a grid (designed grounds), beehives between rows."""
    for i in range(cols):
        for j in range(rows):
            x, z = x0 + i * step, z0 + j * step
            g = ground(x, z)
            r = BUILD.rng(f"orch{x},{z}")
            x += r.randint(-1, 1)          # break the perfect grid a little
            trunk = r.randint(2, 3)
            BUILD.line((x, g + 1, z), (x, g + trunk, z), "minecraft:oak_log[axis=y]")
            canopy = [("minecraft:oak_leaves[persistent=true]", 3),
                      ("minecraft:flowering_azalea_leaves[persistent=true]", 2)]
            cy = g + trunk + 2
            for dx in range(-2, 3):
                for dy in range(-1, 2):
                    for dz in range(-2, 3):
                        d = dx * dx + dz * dz + 2 * dy * dy
                        if d <= 5 and (d < 4 or r.random() < 0.6):
                            put(x + dx, cy + dy, z + dz, canopy)
            BUILD.set(x, cy - 1, z, "minecraft:oak_log[axis=y]")
            mark(x - 2, z - 2, x + 2, z + 2)
    for j in range(rows - 1):
        x, z = x0 + step // 2, z0 + j * step + step // 2
        g = ground(x, z)
        BUILD.set(x, g + 1, z, "minecraft:stripped_oak_log[axis=y]")
        BUILD.set(x, g + 2, z, "minecraft:beehive[facing=south,honey_level=3]")


def woodshed(x0, z0):
    """Open log store: stacked logs under a slab lean-to, chopping block."""
    x1, z1 = x0 + 6, z0 + 3
    mark(x0 - 1, z0 - 1, x1 + 2, z1 + 2)
    for x in (x0, x1):
        BUILD.line((x, 1, z0), (x, 3, z0), "minecraft:stripped_spruce_log[axis=y]")
        BUILD.line((x, 1, z1), (x, 2, z1), "minecraft:stripped_spruce_log[axis=y]")
    BUILD.box((x0, 4, z0), (x1, 4, z0 + 1), "minecraft:spruce_slab[type=bottom]")
    BUILD.box((x0, 3, z0 + 2), (x1, 3, z1), "minecraft:spruce_slab[type=top]")
    BUILD.box((x0 + 1, 1, z0 + 1), (x1 - 1, 2, z0 + 1), [
        ("minecraft:oak_log[axis=x]", 2), ("minecraft:spruce_log[axis=x]", 2),
        ("minecraft:birch_log[axis=x]", 1)])
    BUILD.box((x0 + 1, 1, z0 + 2), (x1 - 3, 1, z0 + 2), "minecraft:spruce_log[axis=x]")
    BUILD.set(x1 + 1, 1, z1 + 1, "minecraft:oak_log[axis=y]")
    BUILD.set(x1 + 1, 2, z1 + 1, "minecraft:oak_slab[type=bottom]")


# --- water features -------------------------------------------------------

def bridge(zc):
    xs = stream_x(zc)
    for z in (zc - 1, zc, zc + 1):
        for o in range(-5, 6):
            x = stream_x(z) + o
            y = 1 if abs(o) <= 2 else (0 if abs(o) <= 4 else 0)
            BUILD.set(x, y, z, "minecraft:spruce_planks" if abs(o) <= 4 else "minecraft:dirt_path")
            occupied.add((x, z))
    for o in range(-4, 5):
        y = 1 if abs(o) <= 2 else 0
        for z in (zc - 2, zc + 2):
            x = stream_x(z) + o
            BUILD.set(x, y + 1, z, "minecraft:spruce_fence")
            occupied.add((x, z))
    for o in (-4, 4):
        for z in (zc - 2, zc + 2):
            x = stream_x(z) + o
            BUILD.set(x, 1, z, "minecraft:stripped_spruce_log[axis=y]")
            BUILD.set(x, 2, z, LANTERN)
    for o in (-2, 2):
        for z in (zc - 1, zc + 1):
            BUILD.line((stream_x(z) + o, -3, z), (stream_x(z) + o, 0, z), "minecraft:stripped_spruce_log[axis=y]")


def dock(z0):
    for z in range(z0, z0 + 3):
        xs = stream_x(z)
        for x in range(xs - 4, xs + 1):
            BUILD.set(x, 0, z, "minecraft:spruce_slab[type=bottom]" if x > xs - 4 else "minecraft:spruce_planks")
            occupied.add((x, z))
    xs = stream_x(z0)
    for z in (z0, z0 + 2):
        BUILD.line((stream_x(z), -3, z), (stream_x(z), 1, z), "minecraft:stripped_spruce_log[axis=y]")
    BUILD.set(stream_x(z0), 2, z0, LANTERN)
    BUILD.set(xs - 2, 1, z0 + 2, "minecraft:barrel[facing=up]")
    BUILD.set(xs - 3, 1, z0 + 2, "minecraft:barrel[facing=up]")


# --- paths, palisade, scatter --------------------------------------------

def path(points, width=3):
    rng_hw = width / 2
    for (ax, az), (bx, bz) in zip(points, points[1:]):
        n = max(abs(bx - ax), abs(bz - az))
        for i in range(n + 1):
            px, pz = ax + (bx - ax) * i / n, az + (bz - az) * i / n
            for dx in range(-2, 3):
                for dz in range(-2, 3):
                    x, z = round(px + dx), round(pz + dz)
                    if math.hypot(x - px, z - pz) > rng_hw or (x, z) in occupied:
                        continue
                    if abs(x - stream_x(z)) <= 3:
                        continue
                    ground_set(x, z, PATH)
                    occupied.add((x, z))


def palisade():
    west, east_margin, north, south = -33, 5, -29, 27
    gate = range(-2, 3)
    pts = ([(x, north) for x in range(west, stream_x(north) - east_margin)] +
           [(x, south) for x in range(west, stream_x(south) - east_margin)] +
           [(west, z) for z in range(north + 1, south)])
    for i, (x, z) in enumerate(pts):
        if z == south and x in gate:
            continue
        g = ground(x, z)
        if (x % 6 == 0 and z in (north, south)) or (x == west and z % 6 == 0):
            BUILD.line((x, g + 1, z), (x, g + 2, z), "minecraft:stripped_spruce_log[axis=y]")
            if (x if z in (north, south) else z) % 12 == 0:
                BUILD.set(x, g + 3, z, LANTERN)
        else:
            BUILD.set(x, g + 1, z, "minecraft:spruce_fence")
        occupied.add((x, z))
    # gatehouse arch
    for x in (-3, 3):
        BUILD.line((x, 1, south), (x, 5, south), "minecraft:stripped_spruce_log[axis=y]")
    BUILD.line((-4, 6, south), (4, 6, south), "minecraft:stripped_spruce_log[axis=x]")
    BUILD.set(-4, 6, south, "minecraft:spruce_stairs[facing=east,half=top]")
    BUILD.set(4, 6, south, "minecraft:spruce_stairs[facing=west,half=top]")
    for x in (-2, 2):
        BUILD.set(x, 5, south, "minecraft:iron_chain[axis=y]")
        BUILD.set(x, 4, south, HANG)
    BUILD.set(0, 7, south, "minecraft:spruce_slab[type=bottom]")


def scatter():
    rng = BUILD.rng("scatter")
    flora = [("minecraft:short_grass", 30), ("minecraft:tall_grass", 8),
             ("minecraft:fern", 6), ("minecraft:bush", 5), ("minecraft:firefly_bush", 2),
             ("minecraft:poppy", 3), ("minecraft:dandelion", 3), ("minecraft:cornflower", 2),
             ("minecraft:oxeye_daisy", 2), ("minecraft:azure_bluet", 2),
              ("minecraft:wildflowers[flower_amount=3,facing=east]", 4),
             ("minecraft:sweet_berry_bush[age=3]", 1)]
    names = [n for n, _ in flora]
    weights = [w for _, w in flora]
    for x in range(X0, X1 + 1):
        for z in range(Z0, Z1 + 1):
            if not in_plate(x, z) or (x, z) in occupied:
                continue
            g = ground(x, z)
            if BUILD.get(x, g, z) != "minecraft:grass_block" or BUILD.get(x, g + 1, z):
                continue
            dens = vnoise(x, z, 6, "meadow")       # where plants grow
            if rng.random() > 0.05 + 0.6 * max(0.0, dens - 0.45):
                continue
            kind = vnoise(x, z, 9, "kind")         # which plants, in patches
            if kind > 0.62:
                blk = rng.choice(["minecraft:poppy", "minecraft:dandelion",
                                  "minecraft:wildflowers[flower_amount=4,facing=east]"])
            elif kind < 0.3:
                blk = rng.choice(["minecraft:cornflower", "minecraft:azure_bluet",
                                  "minecraft:oxeye_daisy", "minecraft:fern"])
            else:
                blk = rng.choices(names, weights)[0]
            if blk == "minecraft:tall_grass":
                BUILD.set(x, g + 1, z, "minecraft:tall_grass[half=lower]")
                BUILD.set(x, g + 2, z, "minecraft:tall_grass[half=upper]")
            else:
                BUILD.set(x, g + 1, z, blk)
    # reeds & lily pads along the stream
    for z in range(Z0, Z1 + 1):
        x = stream_x(z)
        if not in_plate(x, z) or (x, z) in occupied:
            continue
        r = rng.random()
        if r < 0.2:
            bx = x + rng.choice((-3, 3))
            if in_plate(bx, z) and (bx, z) not in occupied:
                BUILD.box((bx, 0, z), (bx, rng.randint(1, 2), z), "minecraft:sugar_cane")
        elif r < 0.35:
            BUILD.set(x + rng.randint(-2, 2), 0, z, "minecraft:lily_pad")


# --- compose --------------------------------------------------------------
with BUILD:
    terrain()
    house()
    barn()
    tower()
    farm()
    pen()
    well(2, 4)
    bridge(-1)
    dock(9)
    orchard(-31, -8, cols=3, rows=3, step=5)
    woodshed(10, -27)
    orchard(20, 14, cols=1, rows=3, step=5)
    # plaza around the well, then paths (paths skip occupied cells)
    for x in range(-4, 9):
        for z in range(-1, 10):
            if math.hypot(x - 2, (z - 4) * 1.2) <= 5.5 and (x, z) not in occupied:
                ground_set(x, z, PLAZA)
                occupied.add((x, z))
    path([(0, 27), (0, 16), (1, 9)], width=3)
    path([(-4, 0), (-4, -2)], width=3)
    path([(6, 2), (11, -4), (13, -8)], width=3)
    path([(-3, 5), (-12, 5), (-18, 5)], width=2)
    path([(7, 5), (13, 6)], width=2)
    path([(-6, 1), (-14, -6), (-21, -14), (-22, -17)], width=2)
    path([(8, 1), (18, -1), (stream_x(-1) - 6, -1)], width=3)
    path([(stream_x(-1) + 6, -1), (X1, -1)], width=3)
    path([(18, 6), (stream_x(9) - 5, 9)], width=2)
    # path lanterns on the main axis
    for z in (12, 20):
        lantern_post(-2, z)
        lantern_post(2, z + 3)
    palisade()
    for x, z, k, h in [(-30, -24, "spruce", 9), (-27, -13, "spruce", 8), (-14, -24, "oak", 5),
                       (-30, 22, "birch", 6), 
                       (23, -22, "birch", 7), (36, -18, "spruce", 8), (36, 12, "oak", 5),
                       (-4, -24, "birch", 6), (25, 25, "spruce", 7), (-14, 24, "oak", 5), (-6, 15, "birch", 6), (12, 23, "spruce", 7),
                       (34, 22, "birch", 6), (-33, -18, "spruce", 7)]:
        if in_plate(x, z):
            tree(x, z, k, h, r=3 if k == "oak" and h >= 6 else 2)
    scatter()
