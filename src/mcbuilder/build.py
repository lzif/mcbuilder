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
from mcbuilder.geometry import Geometry
from mcbuilder.voxels import AIR, VoxelGrid


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
    # Full canonical form (props AND NBT keys sorted): identical blockstates
    # must yield identical palette keys no matter which helper placed them.
    return canonicalize(out)


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
    ) -> Geometry:
        """Fill the box between corners ``c1`` and ``c2`` (inclusive, any order).

        The block string is placed verbatim — no axis/facing guessing.

        Output bounds: ``(|dx| + 1) × (|dy| + 1) × (|dz| + 1)`` cells.

        Returns the placed :class:`Geometry` (absolute coordinates), so
        ``geo.bounds()`` reports the exact footprint — size whatever you
        build next around it (e.g. a chimney through a roof).
        """
        (x1, y1, z1), (x2, y2, z2) = _corners(c1, c2)
        canonical = canonicalize(block)
        geo = Geometry()
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                for z in range(z1, z2 + 1):
                    geo.set(x, y, z, canonical)
        self.place(geo, at=(0, 0, 0))
        return geo

    def walls(
        self, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str
    ) -> Geometry:
        """Hollow box walls between corners (inclusive, any order).

        Places the four vertical walls spanning the full height. No floor
        and no ceiling — use :meth:`box` for those. Verbatim placement.

        Output bounds: same XZ footprint as :meth:`box`, full Y range.

        Returns the placed :class:`Geometry` (absolute coordinates).
        """
        (x1, y1, z1), (x2, y2, z2) = _corners(c1, c2)
        canonical = canonicalize(block)
        geo = Geometry()
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                geo.set(x1, y, z, canonical)
                geo.set(x2, y, z, canonical)
            for x in range(x1 + 1, x2):
                geo.set(x, y, z1, canonical)
                geo.set(x, y, z2, canonical)
        self.place(geo, at=(0, 0, 0))
        return geo

    def floor(
        self, c1: tuple[int, int, int], c2: tuple[int, int, int], block: str
    ) -> Geometry:
        """One-block-thick slab at the lower Y of the two corners, spanning
        the XZ rectangle.

        Documented alias: ``box`` with height 1. Readability sugar for
        agents; placement is verbatim.

        Output bounds: XZ footprint of the corners, 1 thick, at
        ``min(c1.y, c2.y)``.

        Returns the placed :class:`Geometry` (absolute coordinates).
        """
        (x1, y1, z1), (x2, _y2, z2) = _corners(c1, c2)
        return self.box((x1, y1, z1), (x2, y1, z2), block)

    def carve(self, c1: tuple[int, int, int], c2: tuple[int, int, int]) -> None:
        """Remove every cell in the box between corners ``c1`` and ``c2``.

        The exact complement of :meth:`box`: corners are inclusive and
        may be given in any order (same ``_corners`` semantics —
        ``(|dx| + 1) × (|dy| + 1) × (|dz| + 1)`` cells removed).

        Removed cells read as *unset* — ``UNSET`` in
        :meth:`mcbuilder.voxels.VoxelGrid.to_dense`, ``None`` from
        :meth:`get`. That differs from carving with :meth:`set` and
        ``"minecraft:air"``, which leaves a carved *air cell* that the
        exporter can include via ``include_air``.

        Carving a region with no placed cells is a no-op. Must be called
        inside ``with BUILD:``.
        """
        (x1, y1, z1), (x2, y2, z2) = _corners(c1, c2)
        self._require_batch()
        cells = self._grid._cells
        for x in range(x1, x2 + 1):
            for y in range(y1, y2 + 1):
                for z in range(z1, z2 + 1):
                    cells.pop((x, y, z), None)

    # -- direction-computing helper --------------------------------------

    def roof_gable(
        self,
        c1: tuple[int, int, int],
        c2: tuple[int, int, int],
        block: str,
        ridge: str,
        eave_height: int | None = None,
    ) -> Geometry:
        """Gable roof of stairs ascending from both eaves to a ridge line.

        ``ridge`` is required (``"x"`` or ``"z"``, no default): the axis
        the ridge line runs along. The roof footprint is the XZ rectangle
        of the corners.

        ``eave_height`` is the Y of the eave row (the lowest stair row).
        When omitted (the default ``None``) it is inferred as
        ``min(c1.y, c2.y)`` — the corners' Y only sets where the eaves
        sit, exactly as before, so omitting it is fully backward
        compatible. Pass it explicitly to decouple the roof's eave height
        from the corners' Y (e.g. when the corners mark a footprint at
        some other Y).

        Output bounds: the XZ footprint of the corners, rising
        ``ceil(span / 2)`` blocks above the eave height, where ``span``
        is the footprint extent perpendicular to the ridge (the Z extent
        for ``ridge="x"``, the X extent for ``ridge="z"``). E.g. a 5-deep
        span rises 3 blocks; a 6-deep span rises 3 blocks with no ridge
        row.

        Facing rule (computed from geometry, documented here): each row's
        ``facing`` points toward the ridge, i.e. uphill — the tall back
        sits on the high side so every slope reads as a staircase
        climbing to the ridge, matching vanilla. For ``ridge="x"`` the
        eaves are at the Z extremes: north-eave rows (ascending
        southward) face ``south``, south-eave rows face ``north``. For
        ``ridge="z"``: west-eave rows face ``east``, east-eave rows face
        ``west``. The ridge row of an odd-span roof keeps facing the
        min-side eave, so it reads as the top step of the max-side slope.

        ``block`` should be a stair block *without* a ``facing`` property
        (passing one is a :class:`BuildError` — the facing is computed,
        never merged). ``half`` defaults to ``bottom`` when absent; all
        other properties and NBT pass through verbatim.

        Note on preview appearance: each row's tall back faces uphill
        toward the next row up, so consecutive rows interlock with no
        see-through gap — the same closed geometry as a hand-built
        vanilla roof. (An earlier version of this helper faced rows
        downhill, which left real 0.5-block notches; that was a bug,
        fixed in #4.)

        Returns the placed :class:`Geometry` (absolute coordinates), so
        ``geo.bounds()`` reports the exact roof footprint and peak —
        size a chimney (or anything else) around it.
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
        if eave_height is None:
            eave = y1
        elif isinstance(eave_height, bool) or not isinstance(eave_height, int):
            raise BuildError(
                f"roof_gable: eave_height must be an int, got {eave_height!r}"
            )
        else:
            eave = eave_height
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
        geo = Geometry()
        for k in range(pairs):
            y = eave + k
            lo = _emit(name, {**base_props, "facing": eave_hi}, nbt)
            hi = _emit(name, {**base_props, "facing": eave_lo}, nbt)
            for r in range(run_lo, run_hi + 1):
                if ridge == "x":
                    geo.set(r, y, span_lo + k, lo)
                    geo.set(r, y, span_hi - k, hi)
                else:
                    geo.set(span_lo + k, y, r, lo)
                    geo.set(span_hi - k, y, r, hi)
        if span % 2 == 1:
            y = eave + pairs
            c = span_lo + pairs
            ridge_block = _emit(name, {**base_props, "facing": eave_lo}, nbt)
            for r in range(run_lo, run_hi + 1):
                if ridge == "x":
                    geo.set(r, y, c, ridge_block)
                else:
                    geo.set(c, y, r, ridge_block)
        self.place(geo, at=(0, 0, 0))
        return geo

    # -- instancing: stamp Geometry datablocks (Steal #1) ----------------

    def place(self, geometry, *, at: tuple[int, int, int]) -> Geometry:
        """Stamp a :class:`mcbuilder.geometry.Geometry` into the grid.

        Every relative cell ``(dx, dy, dz)`` of the geometry lands at
        ``(at_x + dx, at_y + dy, at_z + dz)``. Last write wins on overlap
        (same rule as :meth:`set`). The geometry is never mutated — one
        instance can be stamped many times.

        This is the op-layer counterpart to the datablock layer
        (``mcbuilder.part.*`` factories): define once, stamp many, with
        explicit coordinates every time (no ``bpy.context``-style
        implicit placement state — the ``at`` keyword has no default).

        Must be called inside ``with BUILD:``. Provenance for all
        stamped cells is the script line calling ``place``.

        Returns the stamped geometry (handy for chaining: the one-shot
        helpers are all built on this).
        """
        self._require_batch()
        if not isinstance(geometry, Geometry):
            raise BuildError(
                f"place: expected a mcbuilder.geometry.Geometry, "
                f"got {type(geometry).__name__}"
            )
        try:
            ax, ay, az = at
        except (TypeError, ValueError):
            raise BuildError(f"place: at must be 3 ints, got {at!r}")
        for v in (ax, ay, az):
            if isinstance(v, bool) or not isinstance(v, int):
                raise BuildError(f"place: at coordinates must be ints, got {v!r}")
        provenance = _caller_provenance()
        for dx, dy, dz, canonical in geometry.cells():
            self._grid.place(ax + dx, ay + dy, az + dz, canonical, provenance)
        return geometry

    # -- parts catalog (PLAN section 4, v0.1) ----------------------------------

    def stairs_run(
        self, start, direction, length=None, block=None, width=1, *, target=None
    ) -> Geometry:
        """Straight staircase ascending towards ``direction``.

        Thin delegate to :func:`mcbuilder.parts.stairs_run` (see it for
        the facing rule and the landing contract). Must be called inside
        ``with BUILD:``.

        Give exactly one of ``length`` / ``target`` (``ValueError`` if
        both or neither). ``target`` is the absolute (x, y, z) the TOP
        step must occupy; the length is derived as
        ``target_y - start_y + 1``. ``ValueError`` if the target isn't
        reachable along ``direction`` from ``start``.

        Output bounds: step ``i`` sits at ``start`` + ``i`` toward
        ``direction`` and ``start_y + i`` up (``i`` in ``0..length-1``);
        ``width`` widens perpendicular toward the positive side.

        Returns the placed :class:`Geometry` (absolute coordinates).
        """
        from mcbuilder import parts

        return parts.stairs_run(
            self, start, direction, length, block, width=width, target=target
        )

    def pillar(self, base, height, block) -> Geometry:
        """Vertical column of ``height`` blocks. Delegate to
        :func:`mcbuilder.parts.pillar`. Must be called inside ``with BUILD:``.

        Output bounds: 1 × ``height`` × 1 at ``base`` (up from ``base.y``).

        Returns the placed :class:`Geometry` (absolute coordinates).
        """
        from mcbuilder import parts

        return parts.pillar(self, base, height, block)

    def railing(self, start, end, block) -> Geometry:
        """Straight horizontal run of blocks. Delegate to
        :func:`mcbuilder.parts.railing`. Must be called inside ``with BUILD:``.

        Output bounds: the straight run from ``start`` to ``end``
        inclusive (axis-aligned).

        Returns the placed :class:`Geometry` (absolute coordinates).
        """
        from mcbuilder import parts

        return parts.railing(self, start, end, block)

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

        Stored raw (a list of ``View`` objects or shorthand strings) and
        normalized downstream by the CLI / render harness. A bare string
        is treated as a single spec, never exploded into characters.
        """
        if views is None:
            self._views_config = None
            return
        if isinstance(views, str):
            views = [views]
        self._views_config = list(views)

    @property
    def grid(self) -> VoxelGrid:
        return self._grid

    @property
    def seed(self):
        return self._seed

    @property
    def views_config(self):
        return self._views_config

    def get(self, x: int, y: int, z: int) -> str | None:
        """The canonical block string at ``(x, y, z)``, or ``None``.

        Returns the block string exactly as stored in the palette
        (e.g. ``"minecraft:oak_stairs[facing=north]"`` — canonical form,
        properties sorted). Returns ``None`` both when the cell was
        never placed *and* when it holds carved ``"minecraft:air"`` —
        there is no observable "empty" block to report.

        Read-only: works outside ``with BUILD:``.
        """
        idx = self._grid._cells.get((x, y, z))
        if idx is None:
            return None
        block = self._grid._palette[idx]
        return None if block == AIR else block

    def count(self, block: str) -> int:
        """Number of cells whose block string equals ``block``.

        ``block`` is canonicalized first (``ValueError`` on malformed
        input), then matched exactly against stored palette entries —
        property order never matters, but the property *set* must match
        verbatim: ``"minecraft:oak_stairs[facing=north]"`` does not
        match a cell holding ``"...[facing=north,half=top]"``.

        Read-only: works outside ``with BUILD:``.
        """
        canonical = canonicalize(block)
        palette = self._grid._palette
        return sum(1 for idx in self._grid._cells.values() if palette[idx] == canonical)

    def find(self, block: str) -> list[tuple[int, int, int]]:
        """Coordinates of every cell holding ``block``, sorted.

        Same matching rule as :meth:`count`: ``block`` is canonicalized,
        then matched exactly. Returns a list of ``(x, y, z)`` tuples in
        ascending ``(x, y, z)`` order (deterministic), or ``[]`` when no
        cell matches.

        Read-only: works outside ``with BUILD:``.
        """
        canonical = canonicalize(block)
        palette = self._grid._palette
        return sorted(
            (x, y, z)
            for (x, y, z), idx in self._grid._cells.items()
            if palette[idx] == canonical
        )

    def validate(self, registry, allowlist=()) -> tuple[list[dict], list[dict]]:
        """Validate this build's palette against a versioned registry.

        The CLI calls this once per run; direct library/harness users call
        it explicitly. It is deliberately NOT run implicitly at ``__exit__``:
        leaving the batch scope cannot assume a registry is available.
        Returns the ``(errors, warnings)`` pair from ``registry.validate``.
        """
        _, palette, _ = self._grid.to_dense()
        return registry.validate(palette, allowlist=allowlist)

    def render(self, out_dir, views=None, assets_dir=None, tier="fast",
               presentation=True, title=None) -> list:
        """Render preview PNGs to ``out_dir``. Returns ordered ``list[Path]``.

        ``tier`` selects the renderer: ``"fast"`` (textured cubes,
        directions untrusted), ``"trusted"`` (PLAN §3 direction-trusted
        tier — orientation-truthful simplified geometry, no textures), or
        ``"faithful"`` (vanilla model geometry + textures, directions
        trusted).

        ``presentation`` and ``title`` apply to the faithful tier only:
        ``presentation=True`` (default) is the Shadow Court look (light
        background, soft shadow, no debug chrome).

        The harness path (PLAN rev 7, section 6): same views produce the same
        files as the CLI's ``previews/`` dir, in the same order as the
        report's views array. View precedence: the explicit ``views``
        argument > this build's ``views_config`` (``Build(views=...)`` /
        ``set_views``) > the default 9-view set. ``views`` may be a list of
        ``View`` objects, a list of shorthand strings, or a single
        semicolon-separated spec string.
        """
        from mcbuilder import preview as preview_mod
        from mcbuilder import preview_trusted as trusted_mod
        from mcbuilder import preview_faithful as faithful_mod
        from mcbuilder import views as views_mod

        if tier not in ("fast", "trusted", "faithful"):
            raise BuildError(
                f"render: tier must be 'fast', 'trusted' or 'faithful', "
                f"got {tier!r}"
            )
        if assets_dir is None:
            # Same discovery as the CLI: fall back to the versioned asset
            # cache instead of silently rendering everything magenta.
            from mcbuilder.config import McbuildConfig
            assets_dir = McbuildConfig().resolve_assets_dir()
        view_list = self._resolve_render_views(views, views_mod)
        if tier == "faithful":
            return list(faithful_mod.render(
                self._grid, out_dir, view_list, assets_dir,
                presentation=presentation, title=title))
        mod = trusted_mod if tier == "trusted" else preview_mod
        return list(mod.render(self._grid, out_dir, view_list, assets_dir))

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
        # Raw View objects: enforce the 36-view cap here (parse_views
        # enforces it for string specs; the CLI enforces it at the end).
        return views_mod.check_cap(views)
