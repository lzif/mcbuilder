"""Geometry factories (``mb.part.*``) — the datablock constructors.

Each factory returns a :class:`mcbuilder.geometry.Geometry`: pure
relative-coordinate voxel data that places nothing. Stamp it with
``BUILD.place(geo, at=(x, y, z))`` inside the ``with BUILD:`` block::

    import mcbuilder as mb

    p = mb.part.pillar(height=5, block="minecraft:oak_log")  # defines, places nothing
    with BUILD:
        BUILD.place(p, at=(0, 0, 0))
        BUILD.place(p, at=(8, 0, 0))

Steal #1 + #3 from ``docs/bpy-design-notes.md``: datablock/instancing
split ("define once, stamp many"), and every public signature here is
**keyword-only** — LLMs mix up positional arg order; keywords are
self-documenting. (The older imperative ``mb.parts.*`` one-shot API
keeps its positional signatures for back-compat and is implemented as
sugar over these factories.)

Direction vocabulary: ``direction`` params use "north"/"south"/"east"/
"west" (case-insensitive). Coordinate frame: +X = east, +Y = up,
+Z = south.
"""

from __future__ import annotations

from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry

__all__ = ["box", "pillar", "railing", "stairs_run"]

# Horizontal step per direction: +X = east, +Z = south.
_DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}

_OPPOSITE: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}


def _merge_props(block: str, extra: dict[str, str]) -> str:
    """Merge ``extra`` props into a block string, overriding existing values.

    (Same helper as the imperative parts layer; duplicated here so this
    module never imports ``mcbuilder.parts`` — the dependency runs the
    other way: ``parts`` is sugar over ``part``.)
    """
    nbt = ""
    rest = block
    brace = rest.find("{")
    if brace != -1:
        nbt = rest[brace:]
        rest = rest[:brace]
    name = rest
    props: dict[str, str] = {}
    lb = rest.find("[")
    if lb != -1:
        rb = rest.rfind("]")
        name = rest[:lb]
        for item in rest[lb + 1 : rb].split(","):
            item = item.strip()
            if not item:
                continue
            key, _, value = item.partition("=")
            props[key.strip()] = value.strip()
    props.update(extra)
    props_str = ",".join(f"{k}={props[k]}" for k in sorted(props))
    merged = f"{name}[{props_str}]" if props_str else name
    return merged + nbt


def _check_direction(direction: str, what: str) -> str:
    dir_key = direction.lower()
    if dir_key not in _DIRECTIONS:
        raise McbuilderError(
            f"{what}: invalid direction {direction!r}; "
            f"expected one of {sorted(_DIRECTIONS)}"
        )
    return dir_key


def box(*, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str) -> Geometry:
    """Relative-coordinate box between corners ``c1`` and ``c2`` (inclusive).

    The block string is placed verbatim — no axis/facing guessing. The
    corners are relative to the geometry origin; ``BUILD.place(geo, at=…)``
    offsets them into the world.
    """
    try:
        (x1, y1, z1), (x2, y2, z2) = tuple(c1), tuple(c2)  # type: ignore[misc]
    except (TypeError, ValueError):
        raise McbuilderError(f"box: corners must each be 3 ints, got {c1!r} and {c2!r}")
    for v in (x1, y1, z1, x2, y2, z2):
        if isinstance(v, bool) or not isinstance(v, int):
            raise McbuilderError(f"box: corner coordinates must be ints, got {v!r}")
    geo = Geometry()
    for x in range(min(x1, x2), max(x1, x2) + 1):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            for z in range(min(z1, z2), max(z1, z2) + 1):
                geo.set(x, y, z, block)
    return geo


def pillar(*, height: int, block: str) -> Geometry:
    """Vertical column of ``height`` blocks from the origin up.

    The ``block`` string is placed verbatim at every level — no props are
    added or altered.
    """
    if isinstance(height, bool) or not isinstance(height, int) or height < 1:
        raise McbuilderError(f"pillar: height must be an int >= 1, got {height!r}")
    geo = Geometry()
    for i in range(height):
        geo.set(0, i, 0, block)
    return geo


def stairs_run(
    *,
    direction: str,
    length: int,
    block: str,
    width: int = 1,
) -> Geometry:
    """Straight staircase ascending towards ``direction``, relative coords.

    Step ``i`` sits at ``(i*dx, i, i*dz)`` — one block of horizontal
    travel per one block of rise, starting at the geometry origin.

    Facing rule (the factory computes this, the agent never hand-guesses):
    each step's stairs block gets ``facing`` = the OPPOSITE of the ascent
    direction, and ``half=bottom`` — stairs face the climber (ascending
    north means facing south), matching the vanilla placement convention.

    ``width > 1`` widens the run along the horizontal axis perpendicular
    to ``direction``, toward the positive side from the origin.
    """
    dir_key = _check_direction(direction, "stairs_run")
    if isinstance(length, bool) or not isinstance(length, int) or length < 1:
        raise McbuilderError(f"stairs_run: length must be an int >= 1, got {length!r}")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise McbuilderError(f"stairs_run: width must be an int >= 1, got {width!r}")
    dx, dz = _DIRECTIONS[dir_key]
    facing = _OPPOSITE[dir_key]
    step_block = _merge_props(block, {"facing": facing, "half": "bottom"})
    px, pz = (0, 1) if dx != 0 else (1, 0)
    geo = Geometry()
    for i in range(length):
        for w in range(width):
            geo.set(i * dx + w * px, i, i * dz + w * pz, step_block)
    return geo


def railing(*, start: tuple[int, int, int], end: tuple[int, int, int], block: str) -> Geometry:
    """Straight horizontal run of blocks, relative coords.

    Must be axis-aligned (x or z constant, y constant) else a
    ``McbuilderError`` is raised. Typically used with fence blocks; the
    game resolves fence/wall connections at paste time, so previews show
    unconnected posts.
    """
    try:
        x1, y1, z1 = tuple(start)
        x2, y2, z2 = tuple(end)
    except (TypeError, ValueError):
        raise McbuilderError(
            f"railing: start/end must each be 3 ints, got {start!r} and {end!r}"
        )
    for v in (x1, y1, z1, x2, y2, z2):
        if isinstance(v, bool) or not isinstance(v, int):
            raise McbuilderError(f"railing: coordinates must be ints, got {v!r}")
    if y1 != y2:
        raise McbuilderError(
            f"railing: start and end must share the same y level "
            f"(got y={y1} and y={y2})"
        )
    if x1 != x2 and z1 != z2:
        raise McbuilderError(
            f"railing: run must be axis-aligned (x or z constant); "
            f"got start={start!r} end={end!r}"
        )
    dist = max(abs(x2 - x1), abs(z2 - z1))
    sx = 0 if x1 == x2 else (1 if x2 > x1 else -1)
    sz = 0 if z1 == z2 else (1 if z2 > z1 else -1)
    geo = Geometry()
    for i in range(dist + 1):
        geo.set(x1 + i * sx, y1, z1 + i * sz, block)
    return geo
