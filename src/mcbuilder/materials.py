"""Material specs: how a shape decides which block goes in each cell.

Anywhere a block is accepted (``BUILD.set``, ``BUILD.box``, every shape in
:mod:`mcbuilder.shapes`, ``Geometry.set``) you may pass a *material spec*:

- ``"minecraft:stone_bricks"`` — one block everywhere.
- ``["minecraft:stone_bricks", ("minecraft:mossy_stone_bricks", 0.4)]`` —
  weighted palette. Bare strings weigh 1. Each cell is picked by a stable
  hash of ``(seed, x, y, z)``, so a cell resolves the same way regardless
  of call order. The result is per-cell "speckle".
- :func:`patches` — the same palette, but picked by smooth noise so
  variants form clusters instead of speckle. Usually what you want for
  large surfaces.
- any callable ``f(x, y, z) -> str`` — full control.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence

from mcbuilder.blocks import canonicalize
from mcbuilder.errors import McbuilderError

__all__ = ["Material", "patches", "resolve_material"]

Material = str | Sequence[str | tuple[str, float]] | Callable[[int, int, int], str]


def _entries(spec) -> list[tuple[str, float]]:
    try:
        items = list(spec)
    except TypeError:
        raise McbuilderError(
            f"invalid material spec {spec!r}: expected a block string, a "
            "sequence of block strings / (block, weight) pairs, or a "
            "callable (x, y, z) -> str"
        )
    out: list[tuple[str, float]] = []
    for e in items:
        if isinstance(e, str):
            out.append((canonicalize(e), 1.0))
        elif isinstance(e, (tuple, list)) and len(e) == 2 and isinstance(e[0], str):
            try:
                w = float(e[1])
            except (TypeError, ValueError):
                raise McbuilderError(f"invalid palette weight {e[1]!r} for {e[0]!r}")
            if w < 0:
                raise McbuilderError(f"negative palette weight {w} for {e[0]!r}")
            out.append((canonicalize(e[0]), w))
        else:
            raise McbuilderError(
                f"invalid palette entry {e!r}: expected a block string or a (block, weight) pair"
            )
    if not out:
        raise McbuilderError("material palette is empty")
    if sum(w for _, w in out) <= 0:
        raise McbuilderError("material palette weights sum to zero")
    return out


def _unit_hash(*key) -> float:
    """Stable hash of ``key`` mapped to ``[0, 1)``."""
    h = hashlib.sha256("\x00".join(map(str, key)).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big") / 2**64


def _pick(entries: list[tuple[str, float]], r: float) -> str:
    """Weighted pick with ``r`` in ``[0, 1)``."""
    target = r * sum(w for _, w in entries)
    acc = 0.0
    for block, w in entries:
        acc += w
        if target < acc:
            return block
    return entries[-1][0]


def resolve_material(spec: Material, x: int, y: int, z: int, seed=None) -> str:
    """Resolve ``spec`` to a canonical block string for cell ``(x, y, z)``.

    ``seed`` salts the palette hash; ``Build`` passes its own seed.
    """
    if isinstance(spec, str):
        return canonicalize(spec)
    if callable(spec):
        return canonicalize(spec(x, y, z))
    return _pick(_entries(spec), _unit_hash(seed, x, y, z))


def patches(palette: Sequence, *, scale: float = 4.0, salt: str = "") -> Callable:
    """Palette picked by smooth 3D value noise: variants form patches.

    ``scale`` is the rough patch size in blocks. Deterministic; change
    ``salt`` to get a different layout from the same palette::

        walls = mb.patches([("minecraft:stone_bricks", 3),
                            "minecraft:mossy_stone_bricks"], scale=3)
        BUILD.walls((0, 0, 0), (9, 5, 9), walls)

    Weights mean "share of the area", approximately: the noise is
    rank-equalized so each variant covers about its weight's share.
    """
    entries = _entries(palette)
    if scale <= 0:
        raise McbuilderError(f"patches: scale must be > 0, got {scale!r}")

    def lattice(ix, iy, iz):
        return _unit_hash("patches", salt, ix, iy, iz)

    def smooth(t):
        return t * t * (3 - 2 * t)

    def noise(x, y, z):
        fx, fy, fz = x / scale, y / scale, z / scale
        ix, iy, iz = math.floor(fx), math.floor(fy), math.floor(fz)
        tx, ty, tz = smooth(fx - ix), smooth(fy - iy), smooth(fz - iz)
        v = 0.0
        for dx, wx in ((0, 1 - tx), (1, tx)):
            for dy, wy in ((0, 1 - ty), (1, ty)):
                for dz, wz in ((0, 1 - tz), (1, tz)):
                    v += wx * wy * wz * lattice(ix + dx, iy + dy, iz + dz)
        return v

    def equalize(v):
        # Trilinear-blended uniform noise piles up around 0.5; a smoothstep
        # pushes it back toward uniform so weights roughly hold.
        v = min(1.0, max(0.0, (v - 0.5) * 1.7 + 0.5))
        return min(0.999999, smooth(v))

    def pick(x, y, z):
        return _pick(entries, equalize(noise(x, y, z)))

    pick.__name__ = "patches"
    return pick
