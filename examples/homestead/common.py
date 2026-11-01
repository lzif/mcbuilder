"""Shared palette and building pieces for the homestead structures.

Every helper takes the ``Build`` to place into as its first argument and
works in that build's coordinates. All four structures sit on y = 0 with
no terrain, so each ``.nbt`` pastes cleanly onto any flat ground.
"""

import mcbuilder as mb

# -- palette -------------------------------------------------------------------
STONE_BASE = mb.patches(
    [
        ("minecraft:stone_bricks", 5),
        ("minecraft:cracked_stone_bricks", 1),
        ("minecraft:mossy_stone_bricks", 2),
        ("minecraft:andesite", 1),
    ],
    scale=2.5,
    salt="stone",
)
FOUNDATION = mb.patches(
    [("minecraft:cobblestone", 4), ("minecraft:mossy_cobblestone", 2), ("minecraft:stone", 1)],
    scale=2,
    salt="foundation",
)
PLASTER = [
    ("minecraft:calcite", 5),
    ("minecraft:smooth_quartz", 1),
    ("minecraft:white_concrete_powder", 1),
]
PLANK_FLOOR = [("minecraft:spruce_planks", 3), ("minecraft:oak_planks", 1)]
BRICK = [("minecraft:bricks", 5), ("minecraft:mud_bricks", 1), ("minecraft:stone_bricks", 1)]
BARN_WALL = mb.patches(
    [
        ("minecraft:spruce_planks", 5),
        ("minecraft:stripped_spruce_wood", 1),
        ("minecraft:dark_oak_planks", 1),
    ],
    scale=2,
    salt="barn",
)
TIMBER = "minecraft:dark_oak_log"
ROOF = "minecraft:deepslate_tile_stairs"
ROOF_EAVE = "minecraft:deepslate_brick_stairs"
VERGE = "minecraft:dark_oak_stairs"
LANTERN = "minecraft:lantern"
HANGING_LANTERN = "minecraft:lantern[hanging=true]"

_OUT = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def even_posts(a: int, b: int, gap: float = 3.5) -> list[int]:
    """Post positions from ``a`` to ``b`` (both included), about ``gap`` apart."""
    n = max(1, round((b - a) / gap))
    return sorted({a + round((b - a) * i / n) for i in range(n + 1)})


def window(build, x, y, z, face, *, tall=2, shutters=True, flower_box=True):
    """Glass-pane window in a wall; ``face`` is the outward direction."""
    ox, oz = _OUT[face]
    sx, sz = (1, 0) if face in ("north", "south") else (0, 1)
    build.line((x, y, z), (x, y + tall - 1, z), "minecraft:glass_pane")
    if shutters:
        for s in (-1, 1):
            build.line(
                (x + ox + s * sx, y, z + oz + s * sz),
                (x + ox + s * sx, y + tall - 1, z + oz + s * sz),
                f"minecraft:spruce_trapdoor[facing={face},half=bottom,open=true]",
            )
    if flower_box:  # greenery resting on a top-half trapdoor ledge
        build.set(x + ox, y - 1, z + oz, "minecraft:flowering_azalea_leaves[persistent=true]")
        if build.get(x + ox, y - 2, z + oz) is None:
            build.set(
                x + ox,
                y - 2,
                z + oz,
                f"minecraft:spruce_trapdoor[facing={face},half=top,open=false]",
            )


def gable_infill(
    build, plane, axis, y0, lo, hi, *, kingpost=True, window_at=None, fill=PLASTER, edge=TIMBER
):
    """Fill the triangle under a gable roof.

    ``axis="x"``: the gable end lies in the plane ``x = plane`` and spans
    ``z = lo..hi`` (the roof's footprint across the ridge); ``"z"`` likewise.
    Timber along the slopes, an optional king post, ``fill`` in between.
    """
    across = "z" if axis == "x" else "x"
    mid = (lo + hi) // 2
    k = 0
    while lo + k + 1 <= hi - k - 1:
        a, b = lo + k + 1, hi - k - 1
        for w in range(a, b + 1):
            if kingpost and w == mid:
                block = f"{edge}[axis=y]"
            elif w in (a, b):
                block = f"{edge}[axis={across}]"
            else:
                block = fill
            build.set(*((plane, y0 + k, w) if axis == "x" else (w, y0 + k, plane)), block)
        k += 1
    if window_at:
        wy, ww = window_at
        for w in (ww - 1, ww + 1):
            build.set(*((plane, wy, w) if axis == "x" else (w, wy, plane)), "minecraft:glass_pane")


def dormer(build, x0, eave_z, eave_y):
    """3-wide gabled dormer on the north slope of a ``ridge="x"`` roof.

    ``eave_z``/``eave_y`` locate the main roof's north eave row; the
    dormer front sits two rows up the slope and its little roof runs back
    to the main ridge.
    """
    fz, fy = eave_z + 2, eave_y + 2
    for x in range(x0, x0 + 3):
        for y in range(fy, fy + 3):
            if x != x0 + 1:
                build.set(x, y, fz, f"{TIMBER}[axis=y]")
            elif y < fy + 2:
                build.set(x, y, fz, "minecraft:glass_pane")
            else:
                build.set(x, y, fz, f"{TIMBER}[axis=x]")
    for x in (x0, x0 + 2):
        for k in (1, 2):
            build.box((x, fy + k, fz + k), (x, fy + 2, fz + k), PLASTER)
    build.roof_gable(
        (x0 - 1, fy + 3, fz - 1), (x0 + 3, fy + 3, fz + 4), ROOF, ridge="z", verge=VERGE
    )
    build.set(x0 + 1, fy + 3, fz, PLASTER)


def lantern_post(build, x, y, z, *, height=2, post="minecraft:spruce_fence"):
    """A post ``height`` tall standing on ``y`` with a lantern on top."""
    build.pillar((x, y, z), height, post)
    build.set(x, y + height, z, LANTERN)
