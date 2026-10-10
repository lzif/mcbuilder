"""Parts catalog (v0.1 seed) — one-shot imperative parts for the mcbuilder DSL.

The agent does composition and proportion (design); the parts own the
geometry math. These one-shot functions are sugar over the datablock
layer: each builds a :class:`mcbuilder.geometry.Geometry` via the
``mcbuilder.part.*`` factories and stamps it with
:meth:`mcbuilder.build.Build.place`. For repeated stamping, use the
factories directly (define once, stamp many).

Coordinate frame (plan §6, carried forward): voxel +X = east, +Y = up, +Z = south.

Parts never enter a batch context themselves — placements must happen
inside the agent's ``with BUILD:`` block. Provenance is captured by
``Build.place`` by skipping mcbuilder-package frames, so the reported
file:line points at the agent's script line that called the part, not at
this module's internals.

Direction vocabulary: ``direction`` params use "north"/"south"/"east"/
"west" (case-insensitive).
"""

from __future__ import annotations

from mcbuilder import part as _part
from mcbuilder.geometry import Geometry

__all__ = ["stairs_run", "pillar", "railing"]


def _at_absolute(geo: Geometry, at: tuple[int, int, int]) -> Geometry:
    """Copy of ``geo`` with cells shifted into absolute coordinates.

    The one-shot helpers stamp a relative-frame factory geometry via
    ``build.place(geo, at=...)``; what they return is this absolute copy,
    so ``.bounds()`` reports where the part actually landed.
    """
    ax, ay, az = at
    out = Geometry()
    for dx, dy, dz, canonical in geo.cells():
        out.set(dx + ax, dy + ay, dz + az, canonical)
    return out


def stairs_run(
    build,
    start: tuple[int, int, int],
    direction: str,
    length: int | None = None,
    block: str | None = None,
    width: int = 1,
    *,
    target: tuple[int, int, int] | None = None,
) -> Geometry:
    """Straight staircase ascending towards ``direction``.

    ``start`` is the (x, y, z) of the FIRST (lowest) step's base position.
    Step ``i`` sits at ``(start_x + i*dx, start_y + i, start_z + i*dz)`` —
    one block of horizontal travel per one block of rise.

    Give exactly one of ``length`` / ``target`` (``ValueError`` if both
    or neither):

    - ``length``: the number of steps (the old contract).
    - ``target``: the absolute (x, y, z) the TOP (highest, last) step
      must occupy — no landing math needed. The run length is derived
      as ``target_y - start_y + 1``: the top step is
      ``start + (length-1)`` toward ``direction`` and ``start_y +
      (length-1)`` up, which equals ``target``. ``ValueError`` if
      ``target`` isn't reachable: it must lie on the 1:1 diagonal from
      ``start`` toward ``direction`` (zero perpendicular offset,
      horizontal travel along the direction equal to the rise, and the
      rise >= 0). ``target == start`` is a valid 1-step run.

    Facing rule (the part computes this, the agent never hand-guesses):
    each step's stairs block gets ``facing`` = the OPPOSITE of the ascent
    direction, and ``half=bottom``. Stairs face the climber, so ascending
    north means facing south, ascending east means facing west, and so on.
    This is also how the vanilla placement convention works (a player
    climbing toward the north places stairs facing south).

    The ``block`` string may carry extra props or NBT — ``facing`` and
    ``half`` are merged in by the part (appended or overridden in the
    canonical block string). Any other props on ``block`` are preserved.

    ``width > 1`` widens the run along the horizontal axis perpendicular
    to ``direction``, extending toward the positive side from ``start``:
    north/south runs widen along +X, east/west runs widen along +Z. The
    top step's base cell (w=0) is the one that lands on ``target``.

    Sugar for ``build.place(mb.part.stairs_run(...), at=start)``.

    Returns the placed :class:`Geometry` (absolute coordinates).
    """
    if block is None:
        raise ValueError("stairs_run: block is required")
    rel_target = None
    if target is not None:
        try:
            tx, ty, tz = tuple(target)
        except (TypeError, ValueError):
            raise ValueError(f"stairs_run: target must be 3 ints, got {target!r}")
        sx, sy, sz = tuple(start)
        rel_target = (tx - sx, ty - sy, tz - sz)
    geo = _part.stairs_run(
        direction=direction, length=length, block=block, width=width,
        target=rel_target,
    )
    build.place(geo, at=start)
    return _at_absolute(geo, start)


def pillar(build, base: tuple[int, int, int], height: int, block: str) -> Geometry:
    """Vertical column of ``height`` blocks starting at ``base`` (inclusive).

    The ``block`` string is placed verbatim at every level — no props are
    added or altered. This is the deliberate contrast with ``stairs_run``:
    generic parts place strings verbatim (cf. plan §6: "no silent
    inference"), and only direction-implying parts compute properties.

    Sugar for ``build.place(mb.part.pillar(...), at=base)``.

    Returns the placed :class:`Geometry` (absolute coordinates).
    """
    geo = _part.pillar(height=height, block=block)
    build.place(geo, at=base)
    return _at_absolute(geo, base)


def railing(
    build,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    block: str,
) -> Geometry:
    """Straight horizontal run of blocks from ``start`` to ``end`` inclusive.

    Must be axis-aligned (x or z constant, y constant across both points)
    else a ``McbuilderError`` is raised naming the problem.

    Typically used with fence blocks. Note for the agent: the exporter
    writes the bare block (``minecraft:oak_fence``) and the *game* resolves
    fence/wall connections at paste time — connections are runtime state,
    not stored blockstate data. So previews will show fences without
    connected arms; the in-game paste will show the correct connected
    shape. (Plan §5: the full faithful renderer is deferred, replaced by the §3 tier;
    ``apply`` model and warns about approximate multipart blocks.)

    Sugar for ``build.place(mb.part.railing(...), at=(0, 0, 0))``.

    Returns the placed :class:`Geometry` (absolute coordinates).
    """
    geo = _part.railing(start=start, end=end, block=block)
    build.place(geo, at=(0, 0, 0))
    return _at_absolute(geo, (0, 0, 0))
