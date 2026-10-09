"""Geometry: relative-coordinate voxel datablocks (the bpy.data layer).

A :class:`Geometry` is pure data: a list of ``(dx, dy, dz, canonical)``
placements in *relative* coordinates. It places nothing on its own —
stamping happens via :meth:`mcbuilder.build.Build.place`, which is the
op-layer counterpart (bpy.ops analog). This is Steal #1 from
``docs/bpy-design-notes.md``: define once, stamp many.

Layering law (Steal #4):

- ``voxels.VoxelGrid.place`` — raw, no canonicalization (bmesh layer)
- ``Build.set`` — canonicalize + provenance (validated op layer)
- ``Geometry`` / ``mcbuilder.part.*`` — pure data, no Build, no placement
  (datablock layer; this module)
- ``Build.place`` — stamp a Geometry into the grid (op layer)
- ``mcbuilder.parts.*`` — one-shot imperative parts, implemented as
  ``place(part.*(...), at=...)`` sugar (op layer)
- the agent's script — the modifier stack (re-run = re-evaluate)

There is deliberately no placement cursor, no "current position", no
implicit state of any kind (the anti-``bpy.context`` rule). Every
:meth:`Build.place` takes explicit coordinates.

Block strings are canonicalized at factory time (``ValueError`` on
malformed input); registry validation still happens later, once per
batch, at the CLI/harness layer.
"""

from __future__ import annotations

from mcbuilder.blocks import canonicalize

__all__ = ["Geometry"]


class Geometry:
    """A reusable, relative-coordinate voxel datablock.

    Instances are built by the ``mcbuilder.part.*`` factories (never by
    hand in agent scripts) and stamped with ``BUILD.place(geo, at=(x,y,z))``.
    Treated as immutable after construction: :meth:`Build.place` never
    mutates the geometry, so one instance can be stamped many times.
    """

    __slots__ = ("_cells",)

    def __init__(self) -> None:
        self._cells: list[tuple[int, int, int, str]] = []

    # -- construction -----------------------------------------------------

    def set(self, dx: int, dy: int, dz: int, block: str) -> None:
        """Record one relative placement (canonicalized).

        The escape hatch for custom geometry that the ``part.*``
        factories don't cover (e.g. a patterned floor): agent-side code
        builds a datablock cell by cell, then stamps it with
        :meth:`Build.place`. Still pure data — no batch requirement, no
        provenance, no validation here.

        Positional args are intentional here (mirroring ``Build.set``) —
        the keyword-only convention (Steal #3) applies to the ``part.*``
        factories and ``Build.place``, not to this voxel-level primitive.
        """
        for v in (dx, dy, dz):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(
                    f"geometry coordinates must be ints, got {v!r}"
                )
        self._cells.append((dx, dy, dz, canonicalize(block)))

    # -- composition (Steal #2: composite parts) --------------------------

    def __add__(self, other: "Geometry") -> "Geometry":
        """Combine two geometries into one (composite part).

        Later cells win on overlap when stamped — same last-write-wins
        rule as :meth:`Build.set`. Neither operand is mutated.
        """
        if not isinstance(other, Geometry):
            return NotImplemented
        out = Geometry()
        out._cells = list(self._cells) + list(other._cells)
        return out

    # -- introspection ----------------------------------------------------

    def cells(self) -> list[tuple[int, int, int, str]]:
        """The relative placements: ``[(dx, dy, dz, canonical), ...]``."""
        return list(self._cells)

    def __len__(self) -> int:
        return len(self._cells)

    def __bool__(self) -> bool:
        return bool(self._cells)

    def bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
        """Inclusive relative bbox, or ``None`` when empty."""
        if not self._cells:
            return None
        xs = [c[0] for c in self._cells]
        ys = [c[1] for c in self._cells]
        zs = [c[2] for c in self._cells]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Geometry({len(self._cells)} cells, bounds={self.bounds()})"
