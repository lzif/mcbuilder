"""Shapes: functions that compute block placements and return a Geometry.

Every function here is pure: it returns a :class:`~mcbuilder.geometry.Geometry`
and places nothing. There are two ways to use one, with identical
arguments:

- ``BUILD.cylinder((0, 0, 0), 4, 10, "minecraft:stone")`` — place it now.
  Every shape is also a ``Build`` method that places the geometry and
  returns it.
- ``tower = mb.shapes.cylinder((0, 0, 0), 4, 10, "minecraft:stone")`` then
  ``BUILD.place(tower, at=(20, 0, 0))`` — define once, stamp many times
  (optionally rotated).

Conventions shared by every shape:

- Coordinates: ``+X`` east, ``+Y`` up, ``+Z`` south. Corners are
  inclusive and may be given in any order.
- ``block`` accepts any material spec (see :mod:`mcbuilder.materials`).
- Shapes that imply a direction (stairs, roofs) compute ``facing``
  themselves; pass the stair block *without* ``facing``.
- ``seed`` salts weighted-palette picks. ``Build`` methods pass the
  build's seed automatically.
"""

from __future__ import annotations

import math

from mcbuilder.blocks import canonicalize, parse
from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry
from mcbuilder.materials import Material, resolve_material

__all__ = [
    "box",
    "walls",
    "pillar",
    "line",
    "stairs",
    "cylinder",
    "sphere",
    "cone",
    "roof_gable",
    "roof_hip",
]

Point = tuple[int, int, int]

#: Horizontal unit step per direction word.
DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}


# ---------------------------------------------------------------------------
# argument checks
# ---------------------------------------------------------------------------


def _point(what: str, p) -> Point:
    try:
        x, y, z = tuple(p)
    except (TypeError, ValueError):
        raise McbuilderError(f"{what} must be 3 ints, got {p!r}")
    for v in (x, y, z):
        if isinstance(v, bool) or not isinstance(v, int):
            raise McbuilderError(f"{what} coordinates must be ints, got {p!r}")
    return x, y, z


def _corners(what: str, c1, c2) -> tuple[Point, Point]:
    x1, y1, z1 = _point(f"{what}: c1", c1)
    x2, y2, z2 = _point(f"{what}: c2", c2)
    return ((min(x1, x2), min(y1, y2), min(z1, z2)), (max(x1, x2), max(y1, y2), max(z1, z2)))


def _positive(what: str, v, minimum: int = 1) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise McbuilderError(f"{what} must be an int >= {minimum}, got {v!r}")
    return v


def _direction(what: str, direction: str) -> str:
    key = str(direction).lower()
    if key not in DIRECTIONS:
        raise McbuilderError(
            f"{what}: invalid direction {direction!r}; expected one of {sorted(DIRECTIONS)}"
        )
    return key


def _with_props(block: str, extra: dict[str, str]) -> str:
    """``block`` with ``extra`` properties merged in (extra wins)."""
    name, props, nbt = parse(block)
    merged = {**props, **extra}
    out = name + (
        "[" + ",".join(f"{k}={merged[k]}" for k in sorted(merged)) + "]" if merged else ""
    )
    return canonicalize(out + (nbt or ""))


class _Painter:
    """Resolves a material spec per cell into a Geometry."""

    def __init__(self, block: Material, seed):
        self.geo = Geometry()
        self._block, self._seed = block, seed
        self._plain = canonicalize(block) if isinstance(block, str) else None

    def block_at(self, x, y, z) -> str:
        return self._plain or resolve_material(self._block, x, y, z, self._seed)

    def put(self, x, y, z, extra: dict[str, str] | None = None) -> None:
        b = self.block_at(x, y, z)
        self.geo.set(x, y, z, _with_props(b, extra) if extra else b)


def _stair_material(what: str, block: Material, seed):
    """Per-cell stair block resolver that refuses a caller-given facing."""

    def at(x, y, z) -> str:
        b = resolve_material(block, x, y, z, seed)
        name, props, nbt = parse(b)
        if "facing" in props:
            raise McbuilderError(
                f"{what} computes 'facing' from the geometry; pass the stair "
                "block without a facing property"
            )
        return b

    at(0, 0, 0)  # fail fast on a plain string with facing
    return at


# ---------------------------------------------------------------------------
# boxes and lines
# ---------------------------------------------------------------------------


def box(c1: Point, c2: Point, block: Material, *, seed=None) -> Geometry:
    """Solid box between corners ``c1`` and ``c2`` (inclusive)."""
    (x1, y1, z1), (x2, y2, z2) = _corners("box", c1, c2)
    p = _Painter(block, seed)
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                p.put(x, y, z)
    return p.geo


def walls(c1: Point, c2: Point, block: Material, *, seed=None) -> Geometry:
    """The four vertical walls of the box ``c1``–``c2``; no floor, no ceiling."""
    (x1, y1, z1), (x2, y2, z2) = _corners("walls", c1, c2)
    p = _Painter(block, seed)
    for y in range(y1, y2 + 1):
        for x in range(x1, x2 + 1):
            for z in range(z1, z2 + 1):
                if x in (x1, x2) or z in (z1, z2):
                    p.put(x, y, z)
    return p.geo


def pillar(base: Point, height: int, block: Material, *, seed=None) -> Geometry:
    """Vertical column of ``height`` blocks going up from ``base``."""
    x, y, z = _point("pillar: base", base)
    height = _positive("pillar: height", height)
    return box((x, y, z), (x, y + height - 1, z), block, seed=seed)


def _round_half_up(v: float) -> int:
    return math.floor(v + 0.5)


def line(p1: Point, p2: Point, block: Material, *, seed=None) -> Geometry:
    """Straight line from ``p1`` to ``p2`` (inclusive), any direction.

    Face-connected: consecutive cells always share a face, so steep
    diagonals never leave blocks touching only at an edge or corner.
    Axis-aligned runs (fences, beams, railings) are just the simple case.
    """
    a = _point("line: p1", p1)
    b = _point("line: p2", p2)
    d = [b[i] - a[i] for i in range(3)]
    n = max(abs(v) for v in d)
    pts = [
        tuple(_round_half_up(a[i] + d[i] * k / n) if n else a[i] for i in range(3))
        for k in range(n + 1)
    ]
    cells: list[Point] = [pts[0]]
    for nxt in pts[1:]:
        cur = list(cells[-1])
        while tuple(cur) != nxt:
            for i in range(3):  # bridge one axis at a time
                if cur[i] != nxt[i]:
                    cur[i] += 1 if nxt[i] > cur[i] else -1
                    break
            cells.append(tuple(cur))
    p = _Painter(block, seed)
    for c in cells:
        p.put(*c)
    return p.geo


def stairs(
    start: Point,
    direction: str,
    block: Material,
    *,
    length: int | None = None,
    target: Point | None = None,
    width: int = 1,
    seed=None,
) -> Geometry:
    """Straight staircase climbing toward ``direction``.

    Step ``i`` sits at ``start + i`` blocks toward ``direction`` and ``i``
    blocks up. Give exactly one of ``length`` (number of steps) or
    ``target`` (the cell the top step must occupy; it must lie on the 1:1
    diagonal from ``start``).

    Each step gets ``facing=<direction>`` and ``half=bottom`` (the tall
    back is uphill, like a staircase placed by a player walking up it).
    ``width`` extends the run sideways toward +X or +Z.
    """
    sx, sy, sz = _point("stairs: start", start)
    key = _direction("stairs", direction)
    dx, dz = DIRECTIONS[key]
    if (length is None) == (target is None):
        raise McbuilderError("stairs: give exactly one of length or target")
    if target is not None:
        tx, ty, tz = _point("stairs: target", target)
        rise = ty - sy
        along = dx * (tx - sx) + dz * (tz - sz)
        across = dz * (tx - sx) - dx * (tz - sz)
        if rise < 0 or along != rise or across != 0:
            raise McbuilderError(
                f"stairs: target {target!r} is not on the 1:1 diagonal from "
                f"{start!r} climbing {key}"
            )
        length = rise + 1
    length = _positive("stairs: length", length)
    width = _positive("stairs: width", width)
    px, pz = (0, 1) if dx else (1, 0)
    stair = _stair_material("stairs", block, seed)
    geo = Geometry()
    for i in range(length):
        for w in range(width):
            x, y, z = sx + i * dx + w * px, sy + i, sz + i * dz + w * pz
            geo.set(x, y, z, _with_props(stair(x, y, z), {"facing": key, "half": "bottom"}))
    return geo


# ---------------------------------------------------------------------------
# round shapes
# ---------------------------------------------------------------------------


def cylinder(
    center: Point,
    radius: int,
    height: int,
    block: Material,
    *,
    axis: str = "y",
    hollow: bool = False,
    fill: Material | None = None,
    seed=None,
) -> Geometry:
    """Cylinder of ``radius`` whose axis starts at ``center``.

    ``axis="y"`` (default) grows ``height`` blocks up; ``"x"`` / ``"z"``
    lie on their side and grow toward +X / +Z (tunnels, pipes, logs).
    ``hollow`` keeps a 1-block shell; ``fill`` (e.g. ``"minecraft:air"``)
    fills the hollow interior so the shape displaces whatever it is
    pasted into.
    """
    cx, cy, cz = _point("cylinder: center", center)
    radius = _positive("cylinder: radius", radius)
    height = _positive("cylinder: height", height)
    if axis not in ("x", "y", "z"):
        raise McbuilderError(f"cylinder: axis must be 'x', 'y' or 'z', got {axis!r}")
    shell, inner = _Painter(block, seed), (_Painter(fill, seed) if fill else None)
    r2, in2 = radius * radius, (radius - 1) ** 2
    for h in range(height):
        for a in range(-radius, radius + 1):
            for b in range(-radius, radius + 1):
                d2 = a * a + b * b
                if d2 > r2:
                    continue
                if axis == "y":
                    pos = (cx + a, cy + h, cz + b)
                elif axis == "x":
                    pos = (cx + h, cy + a, cz + b)
                else:
                    pos = (cx + a, cy + b, cz + h)
                if hollow and d2 <= in2:
                    if inner:
                        inner.put(*pos)
                else:
                    shell.put(*pos)
    return (inner.geo + shell.geo) if inner else shell.geo


def sphere(
    center: Point,
    radius: int,
    block: Material,
    *,
    hollow: bool = False,
    thickness: int = 1,
    dome: bool = False,
    fill: Material | None = None,
    seed=None,
) -> Geometry:
    """Sphere of ``radius`` around ``center``.

    ``dome`` keeps only the upper half (``y >= center.y``). ``hollow``
    keeps a shell ``thickness`` thick; ``fill`` fills the hollow interior.
    """
    cx, cy, cz = _point("sphere: center", center)
    radius = _positive("sphere: radius", radius)
    thickness = _positive("sphere: thickness", thickness)
    shell, inner = _Painter(block, seed), (_Painter(fill, seed) if fill else None)
    r2, in2 = radius * radius, max(0, radius - thickness) ** 2
    for x in range(cx - radius, cx + radius + 1):
        for y in range(cy if dome else cy - radius, cy + radius + 1):
            for z in range(cz - radius, cz + radius + 1):
                d2 = (x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2
                if d2 > r2:
                    continue
                if hollow and d2 <= in2:
                    if inner:
                        inner.put(x, y, z)
                else:
                    shell.put(x, y, z)
    return (inner.geo + shell.geo) if inner else shell.geo


def cone(
    center: Point, radius: int, height: int, block: Material, *, hollow: bool = False, seed=None
) -> Geometry:
    """Upright cone: base disc of ``radius`` at ``center``, tip ``height - 1`` above."""
    cx, cy, cz = _point("cone: center", center)
    radius = _positive("cone: radius", radius)
    height = _positive("cone: height", height)
    p = _Painter(block, seed)
    for i in range(height):
        r = radius * (height - i) / height
        ri = math.ceil(r)
        for x in range(cx - ri, cx + ri + 1):
            for z in range(cz - ri, cz + ri + 1):
                d2 = (x - cx) ** 2 + (z - cz) ** 2
                if d2 > r * r:
                    continue
                interior = d2 <= max(0.0, r - 1) ** 2
                if hollow and interior and not (r < 1 and d2 == 0):
                    continue
                p.put(x, cy + i, z)
    return p.geo


# ---------------------------------------------------------------------------
# roofs
# ---------------------------------------------------------------------------


def roof_gable(
    c1: Point,
    c2: Point,
    block: Material,
    *,
    ridge: str,
    verge: Material | None = None,
    eave: Material | None = None,
    seed=None,
) -> Geometry:
    """Gable roof of stairs over the XZ footprint of ``c1``–``c2``.

    The lowest (eave) row sits at ``min(c1.y, c2.y)``. ``ridge`` is the
    axis the ridge line runs along (``"x"`` or ``"z"``). The roof rises
    ``ceil(span / 2)`` rows, where ``span`` is the footprint size across
    the ridge; an odd span gets a single ridge row.

    Every row faces uphill toward the ridge. Optional trim, both stair
    materials without ``facing``:

    - ``verge``: the two gable-end columns (e.g. wooden bargeboards on a
      tile roof).
    - ``eave``: the lowest row on both slopes.
    """
    if ridge not in ("x", "z"):
        raise McbuilderError(f"roof_gable: ridge must be 'x' or 'z', got {ridge!r}")
    (x1, y0, z1), (x2, _, z2) = _corners("roof_gable", c1, c2)
    body = _stair_material("roof_gable", block, seed)
    verge_m = _stair_material("roof_gable", verge, seed) if verge else None
    eave_m = _stair_material("roof_gable", eave, seed) if eave else None
    if ridge == "x":
        lo, hi, run_lo, run_hi = z1, z2, x1, x2
        face_lo, face_hi = "south", "north"  # slope at lo climbs south
    else:
        lo, hi, run_lo, run_hi = x1, x2, z1, z2
        face_lo, face_hi = "east", "west"
    span = hi - lo + 1
    geo = Geometry()

    def put(across, run, row, facing):
        x, z = (run, across) if ridge == "x" else (across, run)
        y = y0 + row
        mat = body
        if verge_m and run in (run_lo, run_hi):
            mat = verge_m
        elif eave_m and row == 0:
            mat = eave_m
        b = mat(x, y, z)
        geo.set(x, y, z, _with_props(b, {"facing": facing, **_half_default(b)}))

    for row in range(span // 2):
        for run in range(run_lo, run_hi + 1):
            put(lo + row, run, row, face_lo)
            put(hi - row, run, row, face_hi)
    if span % 2:
        row = span // 2
        for run in range(run_lo, run_hi + 1):
            put(lo + row, run, row, face_hi)
    return geo


def _half_default(block: str) -> dict[str, str]:
    return {} if "half" in parse(block)[1] else {"half": "bottom"}


def roof_hip(
    c1: Point, c2: Point, block: Material, *, hip: Material, cap: Material | None = None, seed=None
) -> Geometry:
    """Hip roof: all four sides slope up, one row per block inward.

    ``block`` is the stair material (no ``facing``) for the slopes; ``hip``
    is the full block used on the diagonal hip lines (corners of each
    ring). The top ring that collapses to a line or a single cell is
    filled with ``cap`` (default: ``hip``).
    """
    (x1, y0, z1), (x2, _, z2) = _corners("roof_hip", c1, c2)
    stair = _stair_material("roof_hip", block, seed)
    hip_p = _Painter(hip, seed)
    cap_p = _Painter(cap if cap is not None else hip, seed)
    geo = Geometry()
    k = 0
    while x1 + k <= x2 - k and z1 + k <= z2 - k:
        a, b, c, d, y = x1 + k, x2 - k, z1 + k, z2 - k, y0 + k
        if a == b or c == d:
            for x in range(a, b + 1):
                for z in range(c, d + 1):
                    cap_p.put(x, y, z)
            break
        for x in range(a + 1, b):
            geo.set(x, y, c, _with_props(stair(x, y, c), {"facing": "south", "half": "bottom"}))
            geo.set(x, y, d, _with_props(stair(x, y, d), {"facing": "north", "half": "bottom"}))
        for z in range(c + 1, d):
            geo.set(a, y, z, _with_props(stair(a, y, z), {"facing": "east", "half": "bottom"}))
            geo.set(b, y, z, _with_props(stair(b, y, z), {"facing": "west", "half": "bottom"}))
        for x, z in ((a, c), (b, c), (a, d), (b, d)):
            hip_p.put(x, y, z)
        k += 1
    return geo + hip_p.geo + cap_p.geo
