"""Underwater research base — mcbuilder probe build (agent-authored).

Layout (seabed top surface at y=0, +X east, +Z south):
  - central hub: glass dome r=9 with prismarine ribs, sea-lantern floor ring
  - east tunnel (horizontal tube) -> observation pod (small dome r=5)
  - north tunnel -> moon-pool airlock room (box room, water hole in floor)
  - seabed: mottled sand/gravel/clay disc, kelp, seagrass, coral, pickles

Interior volumes are filled with EXPLICIT air so the paste displaces the
ocean water (run with --include-air); exterior cells stay unset so the
surrounding ocean is untouched.
"""

import math

import mcbuilder as mb

BUILD = mb.Build(seed=42, views=["iso", "az135_el025", "az270_el015", "top"])

AIR = "minecraft:air"
WATER = "minecraft:water"
GLASS = "minecraft:light_blue_stained_glass"
RIB = "minecraft:prismarine_bricks"
DARK = "minecraft:dark_prismarine"
SEABED = [("minecraft:sand", 6), ("minecraft:gravel", 2),
          ("minecraft:clay", 1)]
FLOOR = [(DARK, 3), ("minecraft:prismarine_bricks", 1)]
HULL = [("minecraft:prismarine_bricks", 3), ("minecraft:prismarine", 1)]

HUB_R = 9
POD_C = (22, 1, 0)
POD_R = 6
POOL_Z0, POOL_Z1 = -14, -22  # moon-pool room z extent (north)


# --- helpers the library doesn't have -------------------------------------

def dome_shell_material(cx, cz, ribs=8):
    """Glass with `ribs` vertical prismarine meridian ribs + base band."""
    def mat(x, y, z):
        if y <= 2:
            return RIB
        ang = math.degrees(math.atan2(z - cz, x - cx)) % (360 / ribs)
        near = min(ang, 360 / ribs - ang)
        # rib width in degrees shrinks toward the top so it stays ~1 block
        r_xz = max(1.0, math.hypot(x - cx, z - cz))
        return RIB if near * math.pi / 180 * r_xz < 0.6 else GLASS
    return mat


def tube(axis, start, length, radius, shell, *, glass_top=True):
    """Horizontal tube along 'x' or 'z' (library cylinder is vertical-only).

    Returns (shell_geo, interior_geo) in ABSOLUTE coords; interior is air.
    """
    sx, cy, sz = start
    shell_g, air_g = mb.Geometry(), mb.Geometry()
    step = 1 if length > 0 else -1
    for i in range(0, length, step):
        for dy in range(-radius, radius + 1):
            for dw in range(-radius, radius + 1):
                d2 = dy * dy + dw * dw
                if d2 > radius * radius:
                    continue
                x, z = (sx + i, sz + dw) if axis == "x" else (sx + dw, sz + i)
                y = cy + dy
                if d2 <= (radius - 1) ** 2:
                    air_g.set(x, y, z, AIR)
                else:
                    ring = abs(i) % 4 == 0
                    blk = RIB if (ring or dy < 0 or not glass_top) else GLASS
                    shell_g.set(x, y, z, blk)
    return shell_g, air_g


with BUILD:
    # 1. seabed patch (grounding) -- mottled, 3 deep
    BUILD.cylinder((4, -2, -4), 26, 3, SEABED)

    # 2. hub foundation plinth + dome shell
    BUILD.cylinder((0, 1, 0), HUB_R + 1, 1, HULL)
    BUILD.sphere((0, 1, 0), HUB_R, dome_shell_material(0, 0), hollow=True,
                 dome=True)

    # 3. observation pod + its plinth
    BUILD.cylinder(POD_C, POD_R + 1, 1, HULL)
    BUILD.sphere(POD_C, POD_R, dome_shell_material(POD_C[0], POD_C[2], ribs=6),
                 hollow=True, dome=True)

    # 4. moon-pool room (north): hull box + glass strip windows
    room_c1, room_c2 = (-6, 1, POOL_Z1), (6, 7, POOL_Z0)
    BUILD.box(room_c1, room_c2, HULL)
    for z in range(POOL_Z1 + 2, POOL_Z0, 3):
        BUILD.box((-6, 4, z), (-6, 5, z + 1), GLASS)
        BUILD.box((6, 4, z), (6, 5, z + 1), GLASS)
    # sloped roof trim: slab ring on top
    BUILD.walls((-7, 7, POOL_Z1 - 1), (7, 7, POOL_Z0 + 1),
                "minecraft:prismarine_brick_slab[type=bottom,waterlogged=true]")

    # 5. tunnels (shell first, interior air later)
    east_shell, east_air = tube("x", (HUB_R - 2, 4, 0), POD_C[0] - POD_R - HUB_R + 5, 3, HULL)
    # runs from inside the hub (z=-7) to the room's south wall (z=-14)
    north_shell, north_air = tube("z", (0, 4, -(HUB_R - 2)), POOL_Z0 + (HUB_R - 2) - 1, 3, HULL)
    BUILD.place(east_shell, at=(0, 0, 0))
    BUILD.place(north_shell, at=(0, 0, 0))

    # 6. interiors: explicit air (displaces ocean water on paste)
    BUILD.sphere((0, 1, 0), HUB_R - 1, AIR, dome=True)
    BUILD.sphere(POD_C, POD_R - 1, AIR, dome=True)
    BUILD.box((-5, 2, POOL_Z1 + 1), (5, 6, POOL_Z0 - 1), AIR)
    BUILD.place(east_air, at=(0, 0, 0))
    BUILD.place(north_air, at=(0, 0, 0))

    # 7. floors (overwrite the bottom air layer), tunnel walkways
    BUILD.cylinder((0, 1, 0), HUB_R - 1, 1, FLOOR)
    BUILD.cylinder(POD_C, POD_R - 1, 1, FLOOR)
    BUILD.box((HUB_R - 2, 2, -1), (POD_C[0] - POD_R + 2, 2, 1),
              "minecraft:dark_prismarine_slab[type=bottom]")
    BUILD.box((-1, 2, POOL_Z0), (1, 2, -(HUB_R - 2)),
              "minecraft:dark_prismarine_slab[type=bottom]")
    BUILD.box((-5, 1, POOL_Z1 + 1), (5, 1, POOL_Z0 - 1), FLOOR)

    # 8. moon pool: 3x3 water hole through floor + seabed to open ocean
    BUILD.box((-1, -2, POOL_Z1 + 3), (1, 1, POOL_Z1 + 5), WATER)
    for x, z in ((-2, POOL_Z1 + 2), (2, POOL_Z1 + 2), (-2, POOL_Z1 + 6), (2, POOL_Z1 + 6)):
        BUILD.set(x, 2, z, "minecraft:sea_lantern")

    # 9. lighting: sea-lantern ring in hub floor on the rib rhythm
    for k in range(8):
        a = k * math.pi / 4
        BUILD.set(round(6 * math.cos(a)), 1, round(6 * math.sin(a)),
                  "minecraft:sea_lantern")
    BUILD.set(0, 1, 0, "minecraft:sea_lantern")
    BUILD.set(POD_C[0], 1, POD_C[2], "minecraft:sea_lantern")
    # hanging lantern from the dome apex
    BUILD.line((0, 9, 0), (0, 7, 0), "minecraft:iron_chain[axis=y]")
    BUILD.set(0, 6, 0, "minecraft:lantern[hanging=true]")

    # 10. hub interior props (west half = lab, south = quarters)
    BUILD.box((-6, 2, -2), (-6, 2, 2), "minecraft:barrel[facing=up]")
    BUILD.set(-5, 2, -3, "minecraft:crafting_table")
    BUILD.set(-5, 2, 3, "minecraft:cartography_table")
    BUILD.set(-4, 2, 0, "minecraft:lectern[facing=east]")
    BUILD.set(-2, 2, 5, "minecraft:red_bed[facing=south,part=head]")
    BUILD.set(-2, 2, 4, "minecraft:red_bed[facing=south,part=foot]")
    BUILD.set(2, 2, 5, "minecraft:red_bed[facing=south,part=head]")
    BUILD.set(2, 2, 4, "minecraft:red_bed[facing=south,part=foot]")
    BUILD.set(0, 2, 6, "minecraft:chest[facing=north]")
    BUILD.set(3, 2, -4, "minecraft:brewing_stand")
    BUILD.set(4, 2, -3, "minecraft:spruce_stairs[facing=west]")  # seat

    # 11. pod: conduit on a prismarine pedestal (decorative focal point)
    BUILD.set(POD_C[0], 2, POD_C[2], "minecraft:dark_prismarine")
    BUILD.set(POD_C[0], 3, POD_C[2], "minecraft:conduit[waterlogged=false]")

    # 12. exterior life -- avoid the build footprint
    rng = BUILD.rng("life")

    def free_seabed(x, z):
        if x * x + z * z <= (HUB_R + 2) ** 2:
            return False
        if (x - POD_C[0]) ** 2 + (z - POD_C[2]) ** 2 <= (POD_R + 2) ** 2:
            return False
        if -8 <= x <= 8 and POOL_Z1 - 2 <= z <= -4:
            return False
        if -4 <= z <= 4 and 0 <= x <= 20:
            return False
        return (x - 4) ** 2 + (z + 4) ** 2 <= 24 ** 2

    for _ in range(140):
        x, z = rng.randint(-22, 30), rng.randint(-28, 20)
        if not free_seabed(x, z) or BUILD.get(x, 1, z):
            continue
        roll = rng.random()
        if roll < 0.18:  # kelp column
            h = rng.randint(4, 11)
            BUILD.line((x, 1, z), (x, h - 1, z), "minecraft:kelp_plant")
            BUILD.set(x, h, z, "minecraft:kelp[age=20]")
        elif roll < 0.45:
            BUILD.set(x, 1, z, "minecraft:seagrass")
        elif roll < 0.58:
            BUILD.set(x, 1, z, "minecraft:tall_seagrass[half=lower]")
            BUILD.set(x, 2, z, "minecraft:tall_seagrass[half=upper]")
        elif roll < 0.72:
            coral = rng.choice(["tube", "brain", "bubble", "fire", "horn"])
            BUILD.set(x, 1, z, f"minecraft:{coral}_coral_block")
            BUILD.set(x, 2, z, f"minecraft:{coral}_coral[waterlogged=true]")
        elif roll < 0.85:
            coral = rng.choice(["tube", "brain", "bubble", "fire", "horn"])
            BUILD.set(x, 1, z, f"minecraft:{coral}_coral_fan[waterlogged=true]")
        else:
            BUILD.set(x, 1, z,
                      f"minecraft:sea_pickle[pickles={rng.randint(1, 4)},waterlogged=true]")
