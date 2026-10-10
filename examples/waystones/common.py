"""Shared Geometry factories for the four 7x7x7 waystone variants.

======================================================================
LOSTQOL:WAYSTONE CONTRACT
======================================================================
The center block ``lostqol:waystone`` is a CUSTOM namespaced block. It is
not part of vanilla Minecraft 26.2 — it exists only so the LostQoL
plugin can replace/resolve it at .nbt import time (the plugin-side UGC
import feature, separate scope).

mcbuilder treats it as pass-through: the block is on this directory's
``mcbuild.toml`` allowlist, so validation emits one allowlist WARNING
instead of an error, and the block string is written into the exported
.nbt verbatim. mcbuilder never resolves, models, or previews it —
``mcbuild check`` flagging it as an allowlist warning is EXPECTED.
======================================================================

All factories return pure :class:`mb.Geometry` datablocks (relative
coords, place nothing); stamp them with ``BUILD.place(geo, at=(0,0,0))``.
All signatures are keyword-only per project convention.
"""

import mcbuilder as mb

WAYSTONE = "lostqol:waystone"
_PILLARS = ((1, 1), (1, 5), (5, 1), (5, 5))
_CORNERS = ((0, 0), (0, 6), (6, 0), (6, 6))


def floor_pattern(*, fn) -> mb.Geometry:
    """7x7 floor at y=0; fn(x, z) -> canonical block string."""
    g = mb.Geometry()
    for x in range(7):
        for z in range(7):
            g.set(x, 0, z, fn(x, z))
    return g


def base_step(*, step_block: str, stair_block: str, center_block=None) -> mb.Geometry:
    """5x5 stepped base at y=1 (x,z 1..5): full 3x3 center, stair edges.

    The 12 edge cells are bottom-half stairs facing inward (toward the
    3x3 center = uphill): z=1 faces south, z=5 faces north, x=1 faces
    east, x=5 faces west. The 4 corners are full step_block.
    """
    g = mb.Geometry()
    fill = center_block or step_block
    for x in range(2, 5):
        for z in range(2, 5):
            g.set(x, 1, z, fill)
    for i in range(2, 5):
        g.set(i, 1, 1, f"{stair_block}[facing=south,half=bottom]")
        g.set(i, 1, 5, f"{stair_block}[facing=north,half=bottom]")
        g.set(1, 1, i, f"{stair_block}[facing=east,half=bottom]")
        g.set(5, 1, i, f"{stair_block}[facing=west,half=bottom]")
    for cx, cz in ((1, 1), (1, 5), (5, 1), (5, 5)):
        g.set(cx, 1, cz, step_block)
    return g


def _at(dx: int, dy: int, dz: int, block: str) -> mb.Geometry:
    g = mb.Geometry()
    g.set(dx, dy, dz, block)
    return g


def _set_prop(block: str, key: str, value: str) -> str:
    """Return ``block`` with ``key=value`` set (replacing any existing value).

    Never duplicates a prop — plain string concatenation would produce
    malformed ``[hanging=false,hanging=true]`` if the input already
    carried the key.
    """
    head, sep, tail = block.partition("[")
    props: dict[str, str] = {}
    if sep:
        for item in tail.rstrip("]").split(","):
            item = item.strip()
            if item:
                k, _, v = item.partition("=")
                props[k.strip()] = v.strip()
    props[key] = value
    return f"{head}[{','.join(f'{k}={props[k]}' for k in sorted(props))}]"


def _hanging(block: str, value: str) -> str:
    """Set ``hanging=`` on a lantern block; sea_lantern takes no props."""
    if block.split("[")[0] == "minecraft:sea_lantern":
        return block
    return _set_prop(block, "hanging", value)


def _shift(geo: mb.Geometry, dx: int, dy: int, dz: int) -> mb.Geometry:
    out = mb.Geometry()
    for x, y, z, b in geo.cells():
        out.set(x + dx, y + dy, z + dz, b)
    return out


def corner_lanterns(*, post_block: str, lantern_block: str) -> mb.Geometry:
    """Corner posts at (0/6,1,0/6) with lanterns above at y=2."""
    lantern = _hanging(lantern_block, "false")
    g = mb.Geometry()
    for cx, cz in _CORNERS:
        g += _shift(mb.part.pillar(height=1, block=post_block), cx, 1, cz)
        g += _at(cx, 2, cz, lantern)
    return g


def pillars(*, pillar_block: str) -> mb.Geometry:
    """Four pillars at (1,1),(1,5),(5,1),(5,5), y=2..4."""
    g = mb.Geometry()
    for px, pz in _PILLARS:
        g += _shift(mb.part.pillar(height=3, block=pillar_block), px, 2, pz)
    return g


def pedestal(*, pedestal_block: str, hang_block: str) -> mb.Geometry:
    """Center stack: pedestal y=2, lostqol:waystone y=3, hanging light y=4."""
    hb = _hanging(hang_block, "true")
    return _at(3, 2, 3, pedestal_block) + _at(3, 3, 3, WAYSTONE) + _at(3, 4, 3, hb)


def canopy(*, plate_slab: str, eave_stair: str, corner_block: str, cap_block: str) -> mb.Geometry:
    """Flat canopy: y=5 inner 5x5 plate, outer stair eave, y=6 3x3 cap.

    The 12 middle-edge cells of the 7x7 outer ring are top-half stairs
    facing outward; the 4 true corners are full corner_block. The 8
    ring cells adjacent to the corners are also corner_block so the
    canopy reads as one solid 7x7 plate (deviation from a literal
    12+4 read — gaps there would look broken).
    """
    plate = mb.part.box(c1=(0, 0, 0), c2=(4, 0, 4), block=plate_slab)
    ring = mb.Geometry()
    for i in (2, 3, 4):
        ring.set(i, 0, 0, f"{eave_stair}[facing=north,half=top]")
        ring.set(i, 0, 6, f"{eave_stair}[facing=south,half=top]")
        ring.set(0, 0, i, f"{eave_stair}[facing=west,half=top]")
        ring.set(6, 0, i, f"{eave_stair}[facing=east,half=top]")
    for cx, cz in _CORNERS:
        ring.set(cx, 0, cz, corner_block)
    for kx, kz in ((1, 0), (5, 0), (1, 6), (5, 6), (0, 1), (0, 5), (6, 1), (6, 5)):
        ring.set(kx, 0, kz, corner_block)
    cap = mb.part.box(c1=(0, 0, 0), c2=(2, 0, 2), block=cap_block)
    return _shift(plate, 1, 5, 1) + _shift(ring, 0, 5, 0) + _shift(cap, 2, 6, 2)
