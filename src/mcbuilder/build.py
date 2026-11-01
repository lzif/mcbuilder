"""``Build``: the object a builder script fills with blocks.

A builder script defines a module-level ``BUILD`` and places blocks inside
a ``with BUILD:`` block::

    import mcbuilder as mb

    BUILD = mb.Build(seed=7)

    with BUILD:
        BUILD.box((0, 0, 0), (8, 0, 6), "minecraft:cobblestone")
        BUILD.walls((0, 1, 0), (8, 4, 6), "minecraft:oak_planks")
        BUILD.roof_gable((-1, 5, -1), (9, 5, 7), "minecraft:spruce_stairs", ridge="x")

Placement methods:

- :meth:`Build.set`, :meth:`Build.carve`, :meth:`Build.place` — the primitives.
- Every shape in :mod:`mcbuilder.shapes` (``box``, ``walls``, ``pillar``,
  ``line``, ``stairs``, ``cylinder``, ``sphere``, ``cone``,
  ``roof_gable``, ``roof_hip``) is also a method with the same
  arguments. It places the shape and returns the placed
  :class:`~mcbuilder.geometry.Geometry`, so ``geo.bounds()`` tells you
  exactly what landed.

Blocks are placed verbatim: nothing ever guesses ``facing`` or ``axis``
except shapes whose geometry implies it (stairs, roofs), and those say so.

Determinism: ``seed`` drives every random choice (``BUILD.rng()`` and
weighted palettes), so the same script and seed always give the same build.
"""

from __future__ import annotations

import functools
import os
import random
import sys

from mcbuilder import shapes as _shapes
from mcbuilder.blocks import canonicalize
from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry
from mcbuilder.materials import Material, resolve_material
from mcbuilder.rotation import _check_rotation, _rotate_point, rotate_blockstate
from mcbuilder.voxels import AIR, VoxelGrid

__all__ = ["Build", "BuildError"]


class BuildError(McbuilderError):
    """Misuse of the Build API (placing outside ``with BUILD:``, bad arguments)."""


_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _caller_provenance() -> tuple[str, int] | None:
    """``(filename, lineno)`` of the first stack frame outside this package.

    Errors then point at the line of the user's script, not at library code.
    """
    frame = sys._getframe(1)
    try:
        while frame is not None:
            filename = os.path.abspath(frame.f_code.co_filename)
            if not filename.startswith(_PACKAGE_DIR + os.sep):
                return (frame.f_code.co_filename, frame.f_lineno)
            frame = frame.f_back
    finally:
        del frame
    return None


def _ints(what: str, p) -> tuple[int, int, int]:
    try:
        x, y, z = p
    except (TypeError, ValueError):
        raise BuildError(f"{what} must be 3 ints, got {p!r}")
    for v in (x, y, z):
        if isinstance(v, bool) or not isinstance(v, int):
            raise BuildError(f"{what} coordinates must be ints, got {p!r}")
    return x, y, z


class Build:
    """A voxel build. Placements must happen inside ``with BUILD:``.

    Args:
        seed: drives ``rng()`` and weighted palette picks.
        views: default preview views, e.g. ``["iso", "az135_el025", "top"]``.
        max_dimensions: size limit per axis; exceeding it raises
            :class:`~mcbuilder.voxels.GridBoundsError`.
    """

    def __init__(
        self, seed=None, views=None, max_dimensions: tuple[int, int, int] = (256, 256, 256)
    ):
        self._seed = seed
        self._rng = random.Random(seed)
        self._grid = VoxelGrid(max_dims=max_dimensions)
        self._depth = 0
        self._views = None
        if views is not None:
            self.set_views(views)

    # -- scope -----------------------------------------------------------

    def __enter__(self) -> Build:
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self._depth = max(0, self._depth - 1)
        return False

    def _require_scope(self) -> None:
        if self._depth == 0:
            raise BuildError("placements must be inside `with BUILD:`")

    # -- primitives --------------------------------------------------------

    def set(self, x: int, y: int, z: int, block: Material) -> None:
        """Place one block (any material spec). Last write wins.

        ``"minecraft:air"`` places explicit air: it is exported with
        ``--air explicit`` and clears whatever the structure is pasted into.
        """
        self._require_scope()
        self._grid.place(
            x, y, z, resolve_material(block, x, y, z, self._seed), _caller_provenance()
        )

    def carve(self, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> None:
        """Remove every placed cell in the box ``c1``–``c2`` (inclusive).

        Removed cells become *unset*: they are not exported, so pasting
        leaves the world untouched there. To force air, use
        ``box(c1, c2, "minecraft:air")`` instead.
        """
        self._require_scope()
        (x1, y1, z1), (x2, y2, z2) = (_ints("carve: c1", c1), _ints("carve: c2", c2))
        cells = self._grid._cells
        for x in range(min(x1, x2), max(x1, x2) + 1):
            for y in range(min(y1, y2), max(y1, y2) + 1):
                for z in range(min(z1, z2), max(z1, z2) + 1):
                    cells.pop((x, y, z), None)

    def place(
        self, geometry: Geometry, *, at: tuple[int, int, int] = (0, 0, 0), rotation: str = "NONE"
    ) -> Geometry:
        """Stamp ``geometry`` with its origin at ``at``. Returns what was placed.

        ``rotation`` (``"NONE"``, ``"CLOCKWISE_90"``, ``"CLOCKWISE_180"``,
        ``"COUNTERCLOCKWISE_90"``) turns the geometry about its origin
        first; ``facing``/``axis`` and friends rotate with it. The returned
        geometry is in absolute coordinates.
        """
        self._require_scope()
        if not isinstance(geometry, Geometry):
            raise BuildError(f"place: expected a Geometry, got {type(geometry).__name__}")
        _check_rotation(rotation)
        ax, ay, az = _ints("place: at", at)
        provenance = _caller_provenance()
        placed = Geometry()
        for dx, dy, dz, block in geometry.cells():
            if rotation != "NONE":
                dx, dz = _rotate_point(dx, dz, 0, 0, rotation)
                block = rotate_blockstate(block, rotation)
            x, y, z = ax + dx, ay + dy, az + dz
            self._grid.place(x, y, z, block, provenance)
            placed._cells.append((x, y, z, block))
        return placed

    def recenter(self) -> None:
        """Shift the build so its XZ bounding-box center is at the origin (Y unchanged)."""
        bb = self._grid.bounds()
        if bb is None:
            return
        (minx, _, minz), (maxx, _, maxz) = bb
        self._grid._shift(-((minx + maxx + 1) // 2), 0, -((minz + maxz + 1) // 2))

    # -- reading the build back -------------------------------------------

    def get(self, x: int, y: int, z: int) -> str | None:
        """Canonical block at ``(x, y, z)``; ``None`` if unset or air."""
        idx = self._grid._cells.get((x, y, z))
        if idx is None:
            return None
        block = self._grid._palette[idx]
        return None if block == AIR else block

    def count(self, block: str) -> int:
        """Number of cells holding exactly ``block`` (property order ignored)."""
        canonical = canonicalize(block)
        palette = self._grid._palette
        return sum(1 for idx in self._grid._cells.values() if palette[idx] == canonical)

    def find(self, block: str) -> list[tuple[int, int, int]]:
        """Sorted coordinates of every cell holding exactly ``block``."""
        canonical = canonicalize(block)
        palette = self._grid._palette
        return sorted(p for p, idx in self._grid._cells.items() if palette[idx] == canonical)

    def bounds(self):
        """``((minx, miny, minz), (maxx, maxy, maxz))`` of placed cells, or ``None``."""
        return self._grid.bounds()

    # -- randomness and config ---------------------------------------------

    def rng(self, namespace: str | None = None) -> random.Random:
        """Seeded random generator.

        ``rng()`` is one shared stream. ``rng("roof")`` is an independent
        stream for that name: editing one part of a script then doesn't
        reshuffle the random choices of every other part.
        """
        if namespace is None:
            return self._rng
        if not isinstance(namespace, str):
            raise BuildError(f"rng: namespace must be a string, got {namespace!r}")
        return random.Random(f"{self._seed}\x00{namespace}")

    def set_views(self, views) -> None:
        """Default preview views (a spec string or a list of view tokens)."""
        if views is None:
            self._views = None
            return
        self._views = [views] if isinstance(views, str) else list(views)

    @property
    def grid(self) -> VoxelGrid:
        return self._grid

    @property
    def seed(self):
        return self._seed

    @property
    def views_config(self):
        return self._views

    # -- validation and rendering ------------------------------------------

    def validate(self, registry, allowlist=()) -> tuple[list[dict], list[dict]]:
        """Check every block against ``registry``. Returns ``(errors, warnings)``."""
        _, palette, _ = self._grid.to_dense()
        return registry.validate(palette, allowlist=allowlist)

    def render(
        self,
        out_dir,
        views=None,
        *,
        tier: str = "faithful",
        region=None,
        assets_dir=None,
        title=None,
        presentation: bool = True,
    ) -> list:
        """Render preview PNGs into ``out_dir``; returns the file paths.

        Args:
            views: view spec (defaults to this build's views, then the
                standard 9-view orbit). See :mod:`mcbuilder.render.views`.
            tier: ``"faithful"`` (real models + textures), ``"fast"``
                (textured cubes) or ``"trusted"`` (orientation check).
            region: ``((x0, y0, z0), (x1, y1, z1))`` to render only that
                box — a close-up of one part of a large build.
            presentation: faithful tier only; ``False`` gives the plain
                debug look (dark background, labels).
        """
        from mcbuilder.config import McbuildConfig
        from mcbuilder.render import faithful, fast, trusted
        from mcbuilder.render import views as views_mod

        if tier not in ("fast", "trusted", "faithful"):
            raise BuildError(f"render: tier must be 'fast', 'trusted' or 'faithful', got {tier!r}")
        if assets_dir is None:
            assets_dir = McbuildConfig().resolve_assets_dir()
        view_list = views_mod.resolve(views if views is not None else self._views)
        grid = self._grid
        if region is not None:
            c1, c2 = region
            grid = grid.crop(_ints("render: region", c1), _ints("render: region", c2))
        if tier == "faithful":
            return list(
                faithful.render(
                    grid, out_dir, view_list, assets_dir, presentation=presentation, title=title
                )
            )
        mod = trusted if tier == "trusted" else fast
        return list(mod.render(grid, out_dir, view_list, assets_dir))


def _shape_method(fn):
    """Turn a :mod:`mcbuilder.shapes` function into a placing ``Build`` method."""

    @functools.wraps(fn)
    def method(self, *args, **kwargs):
        kwargs.setdefault("seed", self._seed)
        return self.place(fn(*args, **kwargs))

    method.__doc__ = (fn.__doc__ or "") + (
        "\n\nPlaces the shape and returns the placed Geometry "
        f"(same arguments as ``mb.shapes.{fn.__name__}``)."
    )
    return method


for _name in _shapes.__all__:
    setattr(Build, _name, _shape_method(getattr(_shapes, _name)))
del _name
