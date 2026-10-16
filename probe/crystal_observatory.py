"""Floating Crystal Observatory — probe build (v2).

Archetype:
- Floating sky island: tapered craggy stone/deepslate underbelly with exposed
  amethyst geode heart, hanging stalactites & crystal clusters, moss/stone
  terraced top, plus two detached floating crystal-rock satellite islets.
- Large crystal formations: multi-block angled amethyst + stained-glass crystal
  spires bursting from the island rim and underside.
- Observatory: cylindrical stone & deepslate tower with overhanging cornice,
  small interior (glowing crystal orrery, star-chart lectern, bookshelves,
  ladder to dome deck), cantilevered south viewing deck, and an oxidized-copper
  hemisphere dome with an open shutter slit and a giant refracting telescope.
"""

import math
import mcbuilder as mb

VIEWS = [
    "iso",
    "az045_el025",
    "az135_el025",
    "az225_el025",
    "az315_el025",
    "az180_el015",
    "top",
]

BUILD = mb.Build(seed=42, views=VIEWS)
rng = BUILD.rng()


def mottled(choices: list[tuple[str, float]]) -> str:
    """Weighted random pick using BUILD.rng()."""
    r = rng.random()
    acc = 0.0
    for block, weight in choices:
        acc += weight
        if r <= acc:
            return block
    return choices[-1][0]


ROCK_DARK = [
    ("minecraft:deepslate", 0.45),
    ("minecraft:cobbled_deepslate", 0.35),
    ("minecraft:tuff", 0.20),
]

ROCK_MID = [
    ("minecraft:stone", 0.45),
    ("minecraft:andesite", 0.30),
    ("minecraft:cobblestone", 0.15),
    ("minecraft:tuff", 0.10),
]

TOP_TURF = [
    ("minecraft:moss_block", 0.58),
    ("minecraft:grass_block", 0.28),
    ("minecraft:rooted_dirt", 0.14),
]

WALL_PALETTE = [
    ("minecraft:stone_bricks", 0.50),
    ("minecraft:mossy_stone_bricks", 0.20),
    ("minecraft:cracked_stone_bricks", 0.15),
    ("minecraft:polished_andesite", 0.15),
]

DOME_PALETTE = [
    ("minecraft:oxidized_cut_copper", 0.55),
    ("minecraft:weathered_cut_copper", 0.30),
    ("minecraft:prismarine_bricks", 0.15),
]


def make_floating_islet() -> mb.Geometry:
    """Reusable Geometry datablock for detached floating sky islets."""
    g = mb.Geometry()
    for dx in range(-2, 3):
        for dy in range(-3, 2):
            for dz in range(-2, 3):
                # Tapered inverted mini-cone
                max_r = 2.1 if dy >= 0 else (1.5 if dy == -1 else (0.9 if dy == -2 else 0.4))
                d = math.sqrt(dx * dx + dz * dz)
                if d <= max_r:
                    if dy == 1:
                        g.set(dx, dy, dz, "minecraft:moss_block" if d < 1.5 else "minecraft:stone")
                    elif dy == 0:
                        g.set(dx, dy, dz, "minecraft:stone" if (dx + dz) % 2 == 0 else "minecraft:andesite")
                    else:
                        g.set(dx, dy, dz, "minecraft:cobbled_deepslate")
    # Crystal spire sprouting out of the islet
    for cy in range(1, 5):
        g.set(0, cy, 0, "minecraft:amethyst_block" if cy < 4 else "minecraft:purple_stained_glass")
    g.set(1, 2, 0, "minecraft:amethyst_block")
    g.set(0, 2, 1, "minecraft:purple_stained_glass")
    g.set(0, 5, 0, "minecraft:amethyst_cluster[facing=up]")
    g.set(0, -4, 0, "minecraft:amethyst_cluster[facing=down]")
    return g


def draw_crystal_spire(
    base: tuple[int, int, int],
    direction: tuple[float, float, float],
    length: int,
    base_radius: float,
) -> None:
    """Place a dense, face-connected 3D crystal spire along a vector."""
    bx, by, bz = base
    dx, dy, dz = direction
    norm = math.sqrt(dx * dx + dy * dy + dz * dz)
    dx, dy, dz = dx / norm, dy / norm, dz / norm

    # Half-step sampling guarantees 6-connected voxel continuity (no floating diagonal orphans)
    substeps = length * 2
    last_pos = (bx, by, bz)
    for s in range(substeps + 1):
        t = s / max(1, substeps)
        dist_along = t * length
        cx = bx + dx * dist_along
        cy = by + dy * dist_along
        cz = bz + dz * dist_along
        last_pos = (int(round(cx)), int(round(cy)), int(round(cz)))
        r = max(0.55, base_radius * (1.0 - 0.72 * t))
        ir = int(math.ceil(r))
        for ox in range(-ir, ir + 1):
            for oy in range(-ir, ir + 1):
                for oz in range(-ir, ir + 1):
                    # Octahedral + spherical blend for faceted crystal look
                    d_euclid = math.sqrt(ox * ox + oy * oy + oz * oz)
                    d_oct = (abs(ox) + abs(oy) + abs(oz)) * 0.72
                    dist = 0.6 * d_euclid + 0.4 * d_oct
                    if dist <= r:
                        px, py, pz = int(round(cx + ox)), int(round(cy + oy)), int(round(cz + oz))
                        if dist < r * 0.42 and t < 0.7:
                            blk = "minecraft:sea_lantern" if s % 5 == 0 else "minecraft:budding_amethyst"
                        elif t > 0.80:
                            blk = "minecraft:magenta_stained_glass"
                        elif t > 0.50 and (px + py + pz) % 2 == 0:
                            blk = "minecraft:purple_stained_glass"
                        else:
                            blk = "minecraft:amethyst_block"
                        BUILD.set(px, py, pz, blk)

    # Faceted crystal cluster directly attached to the final voxel
    tx, ty, tz = last_pos
    if dy >= 0:
        BUILD.set(tx, ty + 1, tz, "minecraft:amethyst_cluster[facing=up]")
    else:
        BUILD.set(tx, ty - 1, tz, "minecraft:amethyst_cluster[facing=down]")


ISLET_GEO = make_floating_islet()

with BUILD:
    # =========================================================================
    # 1. FLOATING ISLAND (center=(0, 14, 0), y=3..14)
    # =========================================================================
    for y in range(3, 15):
        t = (y - 3) / 11.0  # 0 at bottom tip, 1 at top surface
        base_r = 0.9 + (t ** 0.72) * 9.6
        ir = int(math.ceil(base_r + 2))
        for x in range(-ir, ir + 1):
            for z in range(-ir, ir + 1):
                angle = math.atan2(z, x)
                lobe = (
                    1.0
                    + 0.14 * math.sin(angle * 3 + 0.7)
                    + 0.10 * math.cos(angle * 5 - 0.4)
                    + 0.06 * math.sin(y * 1.3 + x * 0.5)
                )
                r_eff = base_r * lobe
                dist = math.sqrt(x * x + (z * 0.92) ** 2)
                if dist <= r_eff:
                    if y == 14:
                        if dist > r_eff - 1.3:
                            BUILD.set(x, y, z, mottled(ROCK_MID))
                        else:
                            BUILD.set(x, y, z, mottled(TOP_TURF))
                    elif y >= 11:
                        BUILD.set(x, y, z, mottled(ROCK_MID))
                    else:
                        if dist < 2.0 and y <= 7:
                            BUILD.set(x, y, z, "minecraft:amethyst_block")
                        else:
                            BUILD.set(x, y, z, mottled(ROCK_DARK))

    # Craggy stone & deepslate stalactites dripping from the island underside
    stalactites = [
        (0, 3, 0, 3, "minecraft:amethyst_block"),
        (-3, 6, -2, 3, "minecraft:cobbled_deepslate_wall"),
        (4, 7, 2, 3, "minecraft:cobbled_deepslate_wall"),
        (-5, 9, 3, 2, "minecraft:tuff_wall"),
        (3, 7, -4, 3, "minecraft:cobbled_deepslate_wall"),
        (-2, 5, 2, 3, "minecraft:amethyst_block"),
        (2, 5, -2, 2, "minecraft:amethyst_block"),
    ]
    for sx, sy, sz, h, blk in stalactites:
        BUILD.pillar((sx, sy - h, sz), h, blk)
        if blk == "minecraft:amethyst_block":
            BUILD.set(sx, sy - h - 1, sz, "minecraft:amethyst_cluster[facing=down]")

    # Hanging chains with soul lanterns under the rim
    for cx, cy, cz in [(-6, 10, 4), (6, 10, 4), (0, 9, 7), (-6, 10, -5)]:
        BUILD.pillar((cx, cy - 2, cz), 2, "minecraft:iron_chain[axis=y]")
        BUILD.set(cx, cy - 3, cz, "minecraft:soul_lantern[hanging=true]")

    # =========================================================================
    # 2. LARGE CRYSTAL FORMATIONS + FLOATING SATELLITE ISLETS
    # =========================================================================
    # West primary crystal formation (sweeping up and out)
    draw_crystal_spire(base=(-6, 12, -1), direction=(-0.65, 0.85, -0.15), length=11, base_radius=2.1)
    draw_crystal_spire(base=(-7, 12, 2), direction=(-0.75, 0.68, 0.25), length=8, base_radius=1.3)

    # East-Northeast crystal formation (counterbalancing spire cluster)
    draw_crystal_spire(base=(6, 12, -2), direction=(0.68, 0.82, -0.25), length=10, base_radius=2.0)
    draw_crystal_spire(base=(6, 12, 2), direction=(0.78, 0.62, 0.25), length=7, base_radius=1.3)

    # North-Northwest dorsal crystal formation (frames the observatory from behind)
    draw_crystal_spire(base=(-2, 13, -7), direction=(-0.25, 0.82, -0.65), length=9, base_radius=1.8)

    # Underbelly central crystal root spike (pointing straight down into the void)
    draw_crystal_spire(base=(0, 5, 0), direction=(0.0, -1.0, 0.0), length=5, base_radius=1.6)

    # Surface crystal buds around the island rim
    for bx, bz in [(-5, 5), (5, 5), (-7, -3), (7, 0), (3, -7)]:
        BUILD.set(bx, 15, bz, "minecraft:amethyst_cluster[facing=up]")

    # Two detached floating satellite islets positioned in clear sky across views
    BUILD.place(ISLET_GEO, at=(-15, 9, 4))
    BUILD.place(ISLET_GEO, at=(15, 11, -4))

    # =========================================================================
    # 3. OBSERVATORY TOWER + SMALL INTERIOR (center=(0, y, -1), radius=5.2)
    # =========================================================================
    tower_cx, tower_cz = 0, -1
    tower_r = 5.2

    # Plinth & inlaid floor at y=15
    for x in range(-6, 7):
        for z in range(-7, 6):
            d = math.sqrt((x - tower_cx) ** 2 + (z - tower_cz) ** 2)
            if d <= tower_r + 0.6:
                if d <= tower_r - 1.0:
                    if (x == tower_cx or z == tower_cz) and d < 3.8:
                        BUILD.set(x, 15, z, "minecraft:chiseled_stone_bricks")
                    elif d < 1.6:
                        BUILD.set(x, 15, z, "minecraft:amethyst_block")
                    else:
                        BUILD.set(x, 15, z, "minecraft:spruce_planks")
                else:
                    BUILD.set(x, 15, z, "minecraft:deepslate_bricks")

    # Cylindrical walls y=16..22
    for y in range(16, 23):
        for x in range(-6, 7):
            for z in range(-7, 6):
                dx, dz = x - tower_cx, z - tower_cz
                d = math.sqrt(dx * dx + dz * dz)
                if tower_r - 0.85 <= d <= tower_r + 0.35:
                    if y == 16:
                        BUILD.set(x, y, z, "minecraft:deepslate_bricks")
                    elif y == 19:
                        BUILD.set(x, y, z, "minecraft:chiseled_stone_bricks")
                    elif y == 22:
                        BUILD.set(x, y, z, "minecraft:polished_deepslate")
                    else:
                        BUILD.set(x, y, z, mottled(WALL_PALETTE))
                elif d < tower_r - 0.85:
                    BUILD.carve((x, y, z), (x, y, z))

    # Exterior dark deepslate buttress ribs + cornice lanterns
    rib_offsets = [(-5, 0), (5, 0), (0, -5), (-4, -4), (4, -4), (-4, 4), (4, 4)]
    rib_pillar = mb.part.pillar(height=6, block="minecraft:deepslate_tile_wall")
    for rx, rz in rib_offsets:
        px, pz = tower_cx + rx, tower_cz + rz
        BUILD.set(px, 15, pz, "minecraft:polished_deepslate")
        BUILD.set(px, 16, pz, "minecraft:chiseled_deepslate")
        BUILD.place(rib_pillar, at=(px, 17, pz))
        BUILD.set(px, 22, pz, "minecraft:polished_deepslate")
        BUILD.set(px, 23, pz, "minecraft:lantern")

    # Overhanging cornice trim at y=22 along cardinal walls
    for i in (-2, -1, 0, 1, 2):
        BUILD.set(i, 22, -7, "minecraft:deepslate_brick_stairs[facing=south,half=top]")
        if abs(i) == 2:
            BUILD.set(i, 22, 5, "minecraft:deepslate_brick_stairs[facing=north,half=top]")
        BUILD.set(-6, 22, tower_cz + i, "minecraft:deepslate_brick_stairs[facing=east,half=top]")
        BUILD.set(6, 22, tower_cz + i, "minecraft:deepslate_brick_stairs[facing=west,half=top]")

    # Tall arched stained-glass windows on East, West, North (3 wide x 4 tall frame)
    for wx, wz in [(-5, -1), (5, -1), (0, -6)]:
        for wy in (17, 18, 20, 21):
            BUILD.set(wx, wy, wz, "minecraft:purple_stained_glass")

    # Grand South entrance archway opening onto the viewing deck (x=-1..1, y=16..19, z=4)
    BUILD.carve((-1, 16, 3), (1, 19, 5))
    BUILD.set(-1, 19, 4, "minecraft:deepslate_brick_stairs[facing=west,half=top]")
    BUILD.set(1, 19, 4, "minecraft:deepslate_brick_stairs[facing=east,half=top]")
    BUILD.set(0, 20, 4, "minecraft:sea_lantern")
    BUILD.set(-1, 20, 4, "minecraft:chiseled_deepslate")
    BUILD.set(1, 20, 4, "minecraft:chiseled_deepslate")

    # Small interior details (y=16..19) — visible through the grand archway!
    # Central glowing crystal orrery / focal table
    BUILD.set(0, 16, -1, "minecraft:chiseled_deepslate")
    BUILD.set(0, 17, -1, "minecraft:sea_lantern")
    BUILD.set(0, 18, -1, "minecraft:amethyst_cluster[facing=up]")
    # Bookshelves & star-chart lectern along north interior wall
    for bx in (-2, -1, 1, 2):
        BUILD.set(bx, 16, -4, "minecraft:bookshelf")
        BUILD.set(bx, 17, -4, "minecraft:bookshelf")
    BUILD.set(0, 16, -4, "minecraft:lectern[facing=south]")
    BUILD.set(0, 17, -4, "minecraft:lantern")
    BUILD.set(-3, 16, -2, "minecraft:cartography_table")
    BUILD.set(3, 16, -2, "minecraft:barrel[facing=up]")
    BUILD.set(3, 17, -2, "minecraft:lantern")
    # Ladder up to upper dome gallery on west inside wall
    for ly in range(16, 23):
        BUILD.set(-4, ly, -1, "minecraft:ladder[facing=east]")

    # Upper observation platform floor at y=22 (with hatch opening & central light well)
    for x in range(-4, 5):
        for z in range(-5, 4):
            d = math.sqrt((x - tower_cx) ** 2 + (z - tower_cz) ** 2)
            if d <= tower_r - 0.8:
                BUILD.set(x, 22, z, "minecraft:spruce_slab[type=top]")
    BUILD.carve((-4, 22, -1), (-3, 22, -1))
    BUILD.carve((-1, 22, -2), (1, 22, 0))

    # =========================================================================
    # 4. VIEWING DECK / BALCONY (south side, z=4..9, y=15)
    # =========================================================================
    for x in range(-4, 5):
        for z in range(4, 10):
            if abs(x) == 4 and z == 9:
                continue
            if x in (-4, 4) or z == 9:
                BUILD.set(x, 15, z, "minecraft:deepslate_bricks")
            elif x == 0 and 5 <= z <= 8:
                BUILD.set(x, 15, z, "minecraft:chiseled_stone_bricks")
            else:
                BUILD.set(x, 15, z, "minecraft:spruce_planks")

    # Corbel supports underneath the viewing deck
    for sx in (-3, 0, 3):
        BUILD.set(sx, 14, 7, "minecraft:deepslate_brick_stairs[facing=north,half=top]")
        BUILD.set(sx, 14, 8, "minecraft:deepslate_brick_slab[type=top]")
        BUILD.set(sx, 13, 6, "minecraft:deepslate_brick_stairs[facing=north,half=top]")

    # Viewing deck parapet railing & corner lanterns
    BUILD.railing((-3, 16, 9), (3, 16, 9), "minecraft:deepslate_brick_wall")
    BUILD.railing((-4, 16, 5), (-4, 16, 8), "minecraft:deepslate_brick_wall")
    BUILD.railing((4, 16, 5), (4, 16, 8), "minecraft:deepslate_brick_wall")
    for lx, lz in [(-3, 9), (3, 9), (-4, 5), (4, 5)]:
        BUILD.set(lx, 16, lz, "minecraft:polished_deepslate")
        BUILD.set(lx, 17, lz, "minecraft:lantern")

    # Brass/copper spotting scope on the viewing deck (no untrusted lightning_rod!)
    BUILD.set(2, 16, 7, "minecraft:deepslate_brick_wall")
    BUILD.set(2, 17, 7, "minecraft:cut_copper_slab[type=bottom]")
    BUILD.set(2, 17, 8, "minecraft:end_rod[facing=south]")

    # Exterior entry stairs from the west terrace up to the viewing deck
    BUILD.stairs_run((-6, 14, 6), "east", length=2, block="minecraft:deepslate_brick_stairs", width=2)

    # =========================================================================
    # 5. TELESCOPE DOME + GIANT REFRACTING TELESCOPE (y=23..30)
    # =========================================================================
    dome_r = 5.35
    for dy in range(0, 7):
        y = 23 + dy
        for x in range(-6, 7):
            for z in range(-7, 6):
                dx, dz = x - tower_cx, z - tower_cz
                d3 = math.sqrt(dx * dx + (dy * 1.05) ** 2 + dz * dz)
                if dome_r - 0.95 <= d3 <= dome_r + 0.25:
                    # Open observatory slit facing south (dz >= 0, x in -1..1)
                    if dz >= 0 and -1 <= dx <= 1 and dy >= 1:
                        continue
                    # Framed copper shutter ribs along the slit edges and meridian
                    if dz >= 0 and abs(dx) == 2 and dy >= 1:
                        BUILD.set(x, y, z, "minecraft:waxed_copper_block")
                    elif dx == 0 or dz == 0:
                        BUILD.set(x, y, z, "minecraft:cut_copper")
                    else:
                        BUILD.set(x, y, z, mottled(DOME_PALETTE))

    # Dome finial spire at the zenith
    BUILD.set(tower_cx, 29, tower_cz, "minecraft:polished_deepslate")
    BUILD.set(tower_cx, 30, tower_cz, "minecraft:deepslate_brick_wall")
    BUILD.set(tower_cx, 31, tower_cz, "minecraft:amethyst_cluster[facing=up]")

    # Giant refracting telescope mount + angled barrel emerging from the dome slit!
    # Yoke cradle mount inside the dome at (x=-1..1, y=23..25, z=-1..0)
    BUILD.box((-1, 23, -1), (1, 24, -1), "minecraft:polished_deepslate")
    BUILD.set(-1, 25, 0, "minecraft:polished_deepslate_wall")
    BUILD.set(1, 25, 0, "minecraft:polished_deepslate_wall")

    # Telescope tube: steps diagonally upward and southward from (0, 24, -1) to (0, 31, 6)
    for step in range(8):
        ty = 24 + step
        tz = -1 + step
        tube_blk = "minecraft:deepslate_tiles" if step in (0, 3, 6) else "minecraft:copper_block"
        BUILD.set(0, ty, tz, tube_blk)
        BUILD.set(0, ty + 1, tz, "minecraft:cut_copper_stairs[facing=north,half=bottom]")
        if step > 0:
            BUILD.set(0, ty - 1, tz, "minecraft:cut_copper_stairs[facing=south,half=top]")
        # Side cheek reinforcements along the lower barrel
        if step in (1, 2, 4):
            BUILD.set(-1, ty, tz, "minecraft:dark_oak_trapdoor[facing=west,half=bottom,open=true]")
            BUILD.set(1, ty, tz, "minecraft:dark_oak_trapdoor[facing=east,half=bottom,open=true]")

    # Flared objective lens hood + glowing crystal lens at the front aperture (ty=31, tz=6..7)
    BUILD.set(0, 31, 7, "minecraft:sea_lantern")
    BUILD.set(-1, 31, 6, "minecraft:deepslate_tile_wall")
    BUILD.set(1, 31, 6, "minecraft:deepslate_tile_wall")
    BUILD.set(0, 32, 7, "minecraft:purple_stained_glass")
    BUILD.set(0, 30, 7, "minecraft:purple_stained_glass")
    BUILD.set(-1, 31, 7, "minecraft:purple_stained_glass")
    BUILD.set(1, 31, 7, "minecraft:purple_stained_glass")
    BUILD.set(0, 31, 8, "minecraft:amethyst_cluster[facing=south]")
    # Eyepiece at the bottom-north end of the telescope
    BUILD.set(0, 23, -2, "minecraft:end_rod[facing=north]")
