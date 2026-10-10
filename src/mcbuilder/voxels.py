"""Sparse voxel grid IR: the intermediate representation of a build.

Cells are stored sparsely as ``(x, y, z) -> palette index``; the palette
maps each index to a canonical block string (see :mod:`mcbuilder.blocks`).
:meth:`VoxelGrid.to_dense` materializes the placed region as an int32
numpy array.

Coordinate note: coordinates may be negative (e.g. after
:meth:`mcbuilder.build.Build.recenter` shifts the build so its XZ bbox
center sits at the origin). Each axis accepts ``-max_dim <= c < max_dim``.

Air convention: cells that were never placed read as ``-1`` (unset) in
the dense array. An explicit ``"minecraft:air"`` placement *is* interned
in the palette — carved air stays distinguishable from untouched cells,
which is what the exporter's ``include_air`` flag needs.
"""

from __future__ import annotations

import numpy as np

from mcbuilder.errors import McbuilderError

__all__ = ["McbuilderError", "GridBoundsError", "VoxelGrid", "AIR", "UNSET"]


class GridBoundsError(McbuilderError):
    """A placement fell outside the grid's allowed dimensions."""


AIR = "minecraft:air"

#: Dense-array value for cells that were never placed.
UNSET = -1


class VoxelGrid:
    """Sparse int32-palette voxel grid with a per-axis dimension guard."""

    def __init__(self, max_dims: tuple[int, int, int] = (256, 256, 256)):
        max_dims = tuple(int(d) for d in max_dims)
        if len(max_dims) != 3 or any(d <= 0 for d in max_dims):
            raise ValueError(f"max_dims must be 3 positive ints, got {max_dims!r}")
        self._max_dims: tuple[int, int, int] = max_dims  # type: ignore[assignment]
        self._cells: dict[tuple[int, int, int], int] = {}
        self._palette: list[str] = []
        self._index: dict[str, int] = {}
        self._provenance: dict[int, tuple[str, int]] = {}
        self._overwrites = 0

    @property
    def max_dims(self) -> tuple[int, int, int]:
        return self._max_dims

    def place(
        self,
        x: int,
        y: int,
        z: int,
        canonical: str,
        provenance: tuple[str, int] | None,
    ) -> None:
        """Place ``canonical`` (a canonical block string) at ``(x, y, z)``.

        The block string is interned into the palette (get-or-add) and the
        cell stores its int32 palette index. Overwrites: last write wins.

        ``provenance`` is ``(filename, lineno)`` of the script line that
        caused the placement, or ``None`` when unknown. Recorded per
        *palette index*, first known placement wins.

        Raises :class:`GridBoundsError` naming the offending axis with the
        actual coordinate vs. the allowed dimensions.
        """
        x, y, z = self._coerce_coords(x, y, z)
        self._check_bounds(x, y, z)
        idx = self._index.get(canonical)
        if idx is None:
            idx = len(self._palette)
            self._palette.append(canonical)
            self._index[canonical] = idx
        old = self._cells.get((x, y, z))
        if (
            old is not None
            and old != idx
            and self._palette[old] != AIR
            and canonical != AIR
        ):
            # A real block replaced by a different real block (carving with
            # air, or re-placing the same block, doesn't count).
            self._overwrites += 1
        self._cells[(x, y, z)] = idx
        if provenance is not None and idx not in self._provenance:
            self._provenance[idx] = provenance

    @property
    def overwrite_count(self) -> int:
        """Cells where a real block was replaced by a different real block."""
        return self._overwrites

    def to_dense(self) -> tuple[np.ndarray, list[str], dict[int, tuple[str, int]]]:
        """Materialize the placed region as an int32 array.

        Returns ``(array, palette, provenance)`` where ``array`` has shape
        ``(sx, sy, sz)`` covering the inclusive bbox over *all* placed
        cells — explicit ``"minecraft:air"`` placements expand the dense
        bounds just like real blocks (they are real user intent, e.g. from
        carving), so ``to_dense()`` never crashes on out-of-bbox air and
        never silently drops it. The padding is plain air; exporters and
        renderers treat it as such.

        ``palette`` is index-aligned with the array values, and
        ``provenance`` maps palette index to ``(file, line)``.

        Coordinate mapping: ``array[i, j, k]`` is the cell at
        ``(minx + i, miny + j, minz + k)`` where ``(minx, miny, minz)`` is
        the bbox minimum from :meth:`bounds`. Never-placed cells inside
        the bbox read as ``-1`` (:data:`UNSET`); explicitly carved
        ``"minecraft:air"`` cells read as air's palette index.

        An empty grid (no placed cells at all) returns a ``(0, 0, 0)`` int32
        array.

        The palette is compacted to entries actually referenced by the
        array: placements fully overwritten later leave no phantom entries,
        so validation and block counts never see blocks with zero cells.
        """
        bb = self._placed_bounds()
        if bb is None:
            arr = np.zeros((0, 0, 0), dtype=np.int32)
        else:
            (minx, miny, minz), (maxx, maxy, maxz) = bb
            arr = np.full(
                (maxx - minx + 1, maxy - miny + 1, maxz - minz + 1),
                UNSET,
                dtype=np.int32,
            )
            for (x, y, z), idx in self._cells.items():
                arr[x - minx, y - miny, z - minz] = idx
        palette = list(self._palette)
        provenance = dict(self._provenance)
        # Drop palette entries no cell references (e.g. placements fully
        # overwritten later): phantoms must not be validated or counted.
        used = sorted({int(v) for v in arr.flat if v >= 0})
        if len(used) != len(palette):
            remap = {old: new for new, old in enumerate(used)}
            lookup = np.full(len(palette), UNSET, dtype=np.int32)
            for old, new in remap.items():
                lookup[old] = new
            compacted = np.full(arr.shape, UNSET, dtype=np.int32)
            mask = arr >= 0
            compacted[mask] = lookup[arr[mask]]
            arr = compacted
            palette = [palette[old] for old in used]
            provenance = {
                remap[old]: provenance[old] for old in used if old in provenance
            }
        return arr, palette, provenance

    def _placed_bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
        """Inclusive bbox over *all* placed cells, air included.

        Used by :meth:`to_dense` so an explicit ``"minecraft:air"`` cell
        outside the non-air bbox expands the dense array instead of
        crashing it. ``None`` when nothing was placed at all.
        """
        mins: list[int] | None = None
        maxs: list[int] | None = None
        for x, y, z in self._cells:
            if mins is None:
                mins, maxs = [x, y, z], [x, y, z]
            else:
                assert maxs is not None
                mins[0] = min(mins[0], x)
                mins[1] = min(mins[1], y)
                mins[2] = min(mins[2], z)
                maxs[0] = max(maxs[0], x)
                maxs[1] = max(maxs[1], y)
                maxs[2] = max(maxs[2], z)
        if mins is None or maxs is None:
            return None
        return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])

    def bounds(self) -> tuple[tuple[int, int, int], tuple[int, int, int]] | None:
        """Inclusive ``((minx, miny, minz), (maxx, maxy, maxz))`` bbox.

        Computed over non-air cells only (explicit ``"minecraft:air"``
        placements don't extend the bbox). ``None`` when the grid has no
        non-air cells. Note :meth:`to_dense` deliberately uses a wider
        bbox (see :meth:`_placed_bounds`) so out-of-bbox air can't crash it.
        """
        mins: list[int] | None = None
        maxs: list[int] | None = None
        for (x, y, z), idx in self._cells.items():
            if self._palette[idx] == AIR:
                continue
            if mins is None:
                mins, maxs = [x, y, z], [x, y, z]
            else:
                assert maxs is not None
                mins[0] = min(mins[0], x)
                mins[1] = min(mins[1], y)
                mins[2] = min(mins[2], z)
                maxs[0] = max(maxs[0], x)
                maxs[1] = max(maxs[1], y)
                maxs[2] = max(maxs[2], z)
        if mins is None or maxs is None:
            return None
        return (mins[0], mins[1], mins[2]), (maxs[0], maxs[1], maxs[2])

    def count_non_air(self) -> int:
        """Number of placed cells whose block is not ``minecraft:air``."""
        return sum(1 for idx in self._cells.values() if self._palette[idx] != AIR)

    def _shift(self, dx: int, dy: int, dz: int) -> None:
        """Translate every placed cell by ``(dx, dy, dz)`` in place."""
        if not (dx or dy or dz):
            return
        self._cells = {(x + dx, y + dy, z + dz): idx for (x, y, z), idx in self._cells.items()}

    def _check_bounds(self, x: int, y: int, z: int) -> None:
        for axis, value, allowed in zip("xyz", (x, y, z), self._max_dims):
            if not (-allowed <= value < allowed):
                raise GridBoundsError(
                    f"axis {axis}: coordinate {value} out of bounds "
                    f"(allowed -{allowed}..{allowed - 1} for max dimension {allowed})"
                )

    @staticmethod
    def _coerce_coords(x: int, y: int, z: int) -> tuple[int, int, int]:
        out = []
        for v in (x, y, z):
            if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
                raise TypeError(f"voxel coordinates must be ints, got {v!r}")
            out.append(int(v))
        return out[0], out[1], out[2]
