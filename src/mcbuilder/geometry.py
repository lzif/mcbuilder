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
from mcbuilder.rotation import (
    _check_rotation,
    _rotate_point,
    mirror_blockstate,
    rotate_blockstate,
)

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

    # -- transforms (all return NEW Geometry; self is never mutated) --------

    def shift(self, dx: int, dy: int, dz: int) -> "Geometry":
        """Translate every cell by ``(dx, dy, dz)``. Blockstates untouched."""
        for v in (dx, dy, dz):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(
                    f"shift offsets must be ints, got {v!r}"
                )
        out = Geometry()
        out._cells = [(x + dx, y + dy, z + dz, b)
                      for x, y, z, b in self._cells]
        return out

    def rotate(self, rotation: str = "CLOCKWISE_90", *,
               anchor: tuple[int, int, int] = (0, 0, 0)) -> "Geometry":
        """Rotate every cell about ``anchor`` (cell-corner frame).

        Positions rotate clockwise viewed from above (same convention as
        :func:`mcbuilder.rotation.rotate_position`, but for arbitrary
        anchors instead of square footprints); blockstates rotate per
        :func:`mcbuilder.rotation.rotate_blockstate` — ``facing``,
        ``axis``, sign ``rotation``, cardinal connection keys and
        compound ``orientation`` values are all remapped, so a rotated
        stair assembly keeps pointing the right way.
        """
        _check_rotation(rotation)
        try:
            ax, ay, az = anchor
        except (TypeError, ValueError):
            raise TypeError(
                f"rotate: anchor must be 3 ints, got {anchor!r}"
            )
        for v in (ax, ay, az):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(
                    f"rotate: anchor coordinates must be ints, got {v!r}"
                )
        out = Geometry()
        for x, y, z, b in self._cells:
            rx, rz = _rotate_point(x, z, ax, az, rotation)
            out._cells.append((rx, y, rz, rotate_blockstate(b, rotation)))
        return out

    def mirror(self, axis: str = "x") -> "Geometry":
        """Mirror every cell across the ``axis`` plane through the origin.

        ``axis="x"`` maps ``x → -x``; ``axis="z"`` maps ``z → -z``.
        Blockstates mirror per
        :func:`mcbuilder.rotation.mirror_blockstate` (facing and cardinal
        connection keys swap; see it for the v0 limitations).
        """
        if axis not in ("x", "z"):
            raise TypeError(
                f"mirror: axis must be 'x' or 'z', got {axis!r}"
            )
        out = Geometry()
        for x, y, z, b in self._cells:
            mx, mz = (-x, z) if axis == "x" else (x, -z)
            out._cells.append((mx, y, mz, mirror_blockstate(b, axis)))
        return out

    def carve(self, c1: tuple[int, int, int],
              c2: tuple[int, int, int]) -> "Geometry":
        """Remove every cell in the inclusive relative box ``c1``–``c2``.

        Corners may be given in any order. Returns a new Geometry.
        """
        try:
            (x1, y1, z1), (x2, y2, z2) = tuple(c1), tuple(c2)  # type: ignore[misc]
        except (TypeError, ValueError):
            raise TypeError(
                f"carve: corners must each be 3 ints, got {c1!r} and {c2!r}"
            )
        for v in (x1, y1, z1, x2, y2, z2):
            if isinstance(v, bool) or not isinstance(v, int):
                raise TypeError(
                    f"carve: corner coordinates must be ints, got {v!r}"
                )
        lx, hx = min(x1, x2), max(x1, x2)
        ly, hy = min(y1, y2), max(y1, y2)
        lz, hz = min(z1, z2), max(z1, z2)
        out = Geometry()
        out._cells = [(x, y, z, b) for x, y, z, b in self._cells
                      if not (lx <= x <= hx and ly <= y <= hy and lz <= z <= hz)]
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
