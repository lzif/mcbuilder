"""Builder DSL: the agent-facing construction API.

A builder script defines a module-level ``BUILD`` and places blocks
inside the required ``with BUILD:`` batch scope::

    import mcbuilder as mb

    BUILD = mb.Build(seed=7, views=["orbit:8_el:25", "top"])

    with BUILD:
        BUILD.box((0, 0, 0), (9, 3, 9), "minecraft:stone_bricks")
        BUILD.walls((0, 4, 0), (9, 7, 9), "minecraft:mossy_stone_bricks")

Direction convention (no silent inference): ``box``, ``walls`` and
``floor`` place the block string *verbatim* — no axis or facing is ever
guessed. Only helpers whose geometry implies a direction
(``roof_gable`` here; the parts catalog elsewhere) compute one, and each
documents its rule in its docstring.

Determinism: ``Build(seed=...)`` is the sole RNG source, exposed as
:meth:`Build.rng`. Same script + same seed gives the same grid.
"""

from __future__ import annotations

import math
import os
import random
import sys

from mcbuilder.blocks import canonicalize, parse
from mcbuilder.errors import McbuilderError
from mcbuilder.voxels import VoxelGrid


class BuildError(McbuilderError):
    """Misuse of the Build DSL: placements outside ``with BUILD:``, bad helper args."""


_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_internal(filename: str) -> bool:
    return os.path.abspath(filename).startswith(_PACKAGE_DIR + os.sep)


def _caller_provenance() -> tuple[str, int] | None:
    """``(filename, lineno)`` of the first stack frame outside this package.

    Skips every frame whose file lives inside the ``mcbuilder`` package
    (so helper/parts layers don't shadow the agent's script line).
    ``None`` when no external frame exists.
    """
    frame = sys._getframe(1)
    try:
        while frame is not None:
            filename = frame.f_code.co_filename
            if not _is_internal(filename):
                return (filename, frame.f_lineno)
            frame = frame.f_back
    finally:
        del frame
    return None


def _corners(
    c1: tuple[int, int, int], c2: tuple[int, int, int]
) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Validate two corners and return ``((minx, miny, minz), (maxx, maxy, maxz))``."""
    try:
        (x1, y1, z1), (x2, y2, z2) = tuple(c1), tuple(c2)  # type: ignore[misc]
    except (TypeError, ValueError):
        raise BuildError(f"corners must each be 3 ints, got {c1!r} and {c2!r}")
    for v in (x1, y1, z1, x2, y2, z2):
        if isinstance(v, bool) or not isinstance(v, int):
            raise BuildError(f"corner coordinates must be ints, got {v!r}")
    return (min(x1, x2), min(y1, y2), min(z1, z2)), (max(x1, x2), max(y1, y2), max(z1, z2))


def _emit(name: str, props: dict[str, str], nbt: str | None) -> str:
    out = name
    if props:
        out += "[" + ",".join(f"{k}={props[k]}" for k in sorted(props)) + "]"
    if nbt:
        out += nbt
    return out


def _round_half_up(v: float) -> int:
    return math.floor(v + 0.5)


class Build:
    """Accumulates a voxel build. Placements require the ``with BUILD:`` scope."""

    def __init__(
        self,
        seed=None,
        views=None,
        max_dimensions: tuple[int, int, int] = (256, 256, 256),
    ):
        self._seed = seed
        self._rng = random.Random(seed)
        self._grid = VoxelGrid(max_dims=max_dimensions)
        self._batch_depth = 0
        self._views_config = None
        if views is not None:
            self.set_views(views)

    # -- batch scope -----------------------------------------------------

    def __enter__(self) -> "Build":
        self._batch_depth += 1
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        # Close the batch. Nothing is validated here — registry validation
        # happens once per batch exit at the CLI/harness layer.
        if self._batch_depth > 0:
            self._batch_depth -= 1
        return False

    def _require_batch(self) -> None:
        if self._batch_depth == 0:
            raise BuildError("placements must be inside `with BUILD:`")

    # -- fundamental primitive -------------------------------------------

    def set(self, x: int, y: int, z: int, block: str) -> None:
        """Place one block. Overwrites: last write wins.

        ``"minecraft:air"`` is legal (carving). The block string is
        canonicalized immediately (``ValueError`` on malformed input);
        registry validation happens later, once per batch exit.

        Provenance (``file:line`` of the calling script) is captured per
        palette entry, first placement wins.
        """
        canonical = canonicalize(block)
        self._place(x, y, z, canonical, _caller_provenance())

    def _place(
        self,
        x: int,
        y: int,
        z: int,
        canonical: str,
        provenance: tuple[str, int] | None,
    ) -> None:
        self._require_batch()
        self._grid.place(x, y, z, canonical, provenance)

    # -- massing helpers (verbatim placement, no direction inference) ----

    def box(
        self, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str
    ) -> None:
        """Fill the box between corners ``c1`` and ``c2`` (inclusive, any order).

        The block string is placed verbatim — no axis/facing guessing.
        """
        (x1, y1, z1), (x2, y2, z2) = _corners(c1, c2)
        canonical = canonicalize(block)
        provenance = _caller_provenance()
        self._require_batch()
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                for z in range(z1, z2 + 1):
                    self._grid.place(x, y, z, canonical, provenance)

    def walls(
        self, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str
    ) -> None:
        """Hollow box walls between corners (inclusive, any order).

        Places the four vertical walls spanning the full height. No floor
        and no ceiling — use :meth:`box` for those. Verbatim placement.
        """
        (x1, y1, z1), (x2, y2, z2) = _corners(c1, c2)
        canonical = canonicalize(block)
        provenance = _caller_provenance()
        self._require_batch()
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                self._grid.place(x1, y, z, canonical, provenance)
                self._grid.place(x2, y, z, canonical, provenance)
            for x in range(x1 + 1, x2):
                self._grid.place(x, y, z1, canonical, provenance)
                self._grid.place(x, y, z2, canonical, provenance)

    def floor(
        self, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str
    ) -> None:
        """One-block-thick slab at ``c1``'s Y spanning the XZ rectangle.

        Documented alias: ``box`` with height 1. Readability sugar for
        agents; placement is verbatim.
        """
        (x1, y1, z1), (x2, _y2, z2) = _corners(c1, c2)
        self.box((x1, y1, z1), (x2, y1, z2), block)

    # -- direction-computing helper --------------------------------------

    def roof_gable(
        self,
        c1: tuple[int, int, int],
        c2: tuple[int, int, int],
        block: str,
        ridge: str,
    ) -> None:
        """Gable roof of stairs ascending from both eaves to a ridge line.

        ``ridge`` is required (``"x"`` or ``"z"``, no default): the axis
        the ridge line runs along. The roof footprint is the XZ rectangle
        of the corners; it rises from ``min(c1.y, c2.y)`` (the eave
        height — the corners' Y only sets where the eaves sit).

        Facing rule (computed from geometry, documented here): each row's
        ``facing`` points toward the eave it ascends from, i.e. downhill.
        For ``ridge="x"`` the eaves are at the Z extremes: north-eave rows
        face ``north``, south-eave rows face ``south``. For ``ridge="z"``:
        west-eave rows face ``west``, east-eave rows face ``east``. The
        ridge row of an odd-span roof faces the min-side eave.

        ``block`` should be a stair block *without* a ``facing`` property
        (passing one is a :class:`BuildError` — the facing is computed,
        never merged). ``half`` defaults to ``bottom`` when absent; all
        other properties and NBT pass through verbatim.
        """
        if ridge not in ("x", "z"):
            raise BuildError(f"roof_gable: ridge must be 'x' or 'z', got {ridge!r}")
        name, props, nbt = parse(block)  # ValueError on malformed
        if "facing" in props:
            raise BuildError(
                "roof_gable computes 'facing' from the roof geometry; "
                "pass the stair block without a facing property"
            )
        base_props = dict(props)
        base_props.setdefault("half", "bottom")
        (x1, y1, z1), (x2, _y2, z2) = _corners(c1, c2)
        if ridge == "x":
            span_lo, span_hi = z1, z2
            run_lo, run_hi = x1, x2
            eave_lo, eave_hi = "north", "south"
        else:
            span_lo, span_hi = x1, x2
            run_lo, run_hi = z1, z2
            eave_lo, eave_hi = "west", "east"
        span = span_hi - span_lo + 1
        pairs = span // 2
        provenance = _caller_provenance()
        self._require_batch()
        for k in range(pairs):
            y = y1 + k
            lo = _emit(name, {**base_props, "facing": eave_lo}, nbt)
            hi = _emit(name, {**base_props, "facing": eave_hi}, nbt)
            for r in range(run_lo, run_hi + 1):
                if ridge == "x":
                    self._grid.place(r, y, span_lo + k, lo, provenance)
                    self._grid.place(r, y, span_hi - k, hi, provenance)
                else:
                    self._grid.place(span_lo + k, y, r, lo, provenance)
                    self._grid.place(span_hi - k, y, r, hi, provenance)
        if span % 2 == 1:
            y = y1 + pairs
            c = span_lo + pairs
            ridge_block = _emit(name, {**base_props, "facing": eave_lo}, nbt)
            for r in range(run_lo, run_hi + 1):
                if ridge == "x":
                    self._grid.place(r, y, c, ridge_block, provenance)
                else:
                    self._grid.place(c, y, r, ridge_block, provenance)

    # -- parts catalog (PLAN section 4.2) -------------------------------------

    def stairs_run(self, start, direction, length, block, width=1) -> None:
        """Straight staircase ascending towards ``direction``.

        Thin delegate to :func:`mcbuilder.parts.stairs_run` (see it for the
        facing rule). Must be called inside ``with BUILD:``.
        """
        from mcbuilder import parts

        parts.stairs_run(self, start, direction, length, block, width=width)

    def pillar(self, base, height, block) -> None:
        """Vertical column of ``height`` blocks. Delegate to
        :func:`mcbuilder.parts.pillar`. Must be called inside ``with BUILD:``.
        """
        from mcbuilder import parts

        parts.pillar(self, base, height, block)

    def railing(self, start, end, block) -> None:
        """Straight horizontal run of blocks. Delegate to
        :func:`mcbuilder.parts.railing`. Must be called inside ``with BUILD:``.
        """
        from mcbuilder import parts

        parts.railing(self, start, end, block)

    # -- post-processing --------------------------------------------------

    def recenter(self) -> None:
        """Shift the grid so the bbox center (XZ only; Y untouched) sits at origin.

        Mutates in place. Call after placements, before render/export.
        The center is rounded to the nearest voxel (half up); an empty
        grid is a no-op.
        """
        bb = self._grid.bounds()
        if bb is None:
            return
        (minx, _miny, minz), (maxx, _maxy, maxz) = bb
        dx = -_round_half_up((minx + maxx) / 2)
        dz = -_round_half_up((minz + maxz) / 2)
        self._grid._shift(dx, 0, dz)

    # -- config / introspection -------------------------------------------

    def rng(self) -> random.Random:
        """The sole RNG source for this build, seeded from ``seed``."""
        return self._rng

    def set_views(self, views) -> None:
        """Store view configuration. Pure config — no side effects.

        Accepts a list of ``View`` objects or shorthand strings. The
        ``mcbuilder.views`` module may not exist yet, so it is imported
        lazily; when absent the raw config is stored as-is.
        """
        if views is None:
            self._views_config = None
            return
        try:
            from mcbuilder.views import normalize_views
        except ImportError:
            self._views_config = list(views)
        else:
            self._views_config = normalize_views(views)

    @property
    def grid(self) -> VoxelGrid:
        return self._grid

    @property
    def seed(self):
        return self._seed

    @property
    def views_config(self):
        return self._views_config

    def render(self, out_dir, views=None, assets_dir=None) -> list:
        """Render preview PNGs to ``out_dir``. Returns ordered ``list[Path]``.

        The harness path (PLAN section 4.4): same views produce the same
        files as the CLI's ``previews/`` dir, in the same order as the
        report's views array. View precedence: the explicit ``views``
        argument > this build's ``views_config`` (``Build(views=...)`` /
        ``set_views``) > the default 9-view set. ``views`` may be a list of
        ``View`` objects, a list of shorthand strings, or a single
        semicolon-separated spec string.
        """
        from mcbuilder import preview as preview_mod
        from mcbuilder import views as views_mod

        view_list = self._resolve_render_views(views, views_mod)
        return list(preview_mod.render(self._grid, out_dir, view_list, assets_dir))

    def _resolve_render_views(self, views, views_mod) -> list:
        if views is None:
            views = self._views_config
        if views is None:
            return views_mod.default_views()
        if isinstance(views, str):
            return views_mod.parse_views(views)
        views = list(views)
        if views and isinstance(views[0], str):
            return views_mod.parse_views(";".join(views))
        return views
