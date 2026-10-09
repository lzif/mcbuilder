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

__all__ = ["stairs_run", "pillar", "railing"]


def stairs_run(
    build,
    start: tuple[int, int, int],
    direction: str,
    length: int,
    block: str,
    width: int = 1,
) -> None:
    """Straight staircase ascending towards ``direction``.

    ``start`` is the (x, y, z) of the FIRST (lowest) step's base position.
    Step ``i`` sits at ``(start_x + i*dx, start_y + i, start_z + i*dz)`` —
    one block of horizontal travel per one block of rise.

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
    north/south runs widen along +X, east/west runs widen along +Z.

    Sugar for ``build.place(mb.part.stairs_run(...), at=start)``.
    """
    build.place(
        _part.stairs_run(
            direction=direction, length=length, block=block, width=width
        ),
        at=start,
    )


def pillar(build, base: tuple[int, int, int], height: int, block: str) -> None:
    """Vertical column of ``height`` blocks starting at ``base`` (inclusive).

    The ``block`` string is placed verbatim at every level — no props are
    added or altered. This is the deliberate contrast with ``stairs_run``:
    generic parts place strings verbatim (cf. plan §6: "no silent
    inference"), and only direction-implying parts compute properties.

    Sugar for ``build.place(mb.part.pillar(...), at=base)``.
    """
    build.place(_part.pillar(height=height, block=block), at=base)


def railing(
    build,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    block: str,
) -> None:
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
    """
    build.place(_part.railing(start=start, end=end, block=block), at=(0, 0, 0))
