"""Parts catalog (v0.1 seed) — parameterized geometric parts for the mcbuilder DSL.

The agent does composition and proportion (design); the parts own the
geometry math. Every part in the catalog must pass the positioning test in
plan §10: *fewer script lines, same detail*. A part that simplifies by
dropping detail fails the thesis.

Coordinate frame (plan §4.1): voxel +X = east, +Y = up, +Z = south.

Parts call ``build.set(x, y, z, block)`` and nothing else. Placements must
happen inside the agent's ``with BUILD:`` block — the parts never enter a
batch context themselves. Provenance is captured by ``Build.set`` by
skipping mcbuilder-package frames, so the reported file:line points at the
agent's script line that called the part, not at this module's internals.

Direction vocabulary: ``direction`` params use "north"/"south"/"east"/
"west" (case-insensitive).
"""

from __future__ import annotations

# Horizontal step per direction: +X = east, +Z = south (plan §4.1).
_DIRECTIONS: dict[str, tuple[int, int]] = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}

_OPPOSITE: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
}


def _merge_props(block: str, extra: dict[str, str]) -> str:
    """Merge ``extra`` props into a block string, overriding existing values.

    Parses ``name[props]{nbt}`` into name / props / NBT, applies ``extra``
    (overriding any prop that is already present), then re-renders with
    alphabetically sorted props. The canonical block string is normalized
    via ``mcbuilder.blocks.canonicalize`` (lazy import — that module is
    owned by the validator and must not be imported at module scope here,
    or we risk a circular import).

    Fallback: if ``mcbuilder.blocks`` is not yet importable (e.g. the
    validator module hasn't landed), the locally-merged string is returned
    as-is — it is already deterministic (sorted props), so behavior is
    stable either way; the only difference is the validator's final
    normalization pass.
    """
    nbt = ""
    rest = block
    brace = rest.find("{")
    if brace != -1:
        nbt = rest[brace:]
        rest = rest[:brace]
    name = rest
    props: dict[str, str] = {}
    lb = rest.find("[")
    if lb != -1:
        rb = rest.rfind("]")
        name = rest[:lb]
        for part in rest[lb + 1 : rb].split(","):
            part = part.strip()
            if not part:
                continue
            key, _, value = part.partition("=")
            props[key.strip()] = value.strip()
    props.update(extra)
    props_str = ",".join(f"{k}={props[k]}" for k in sorted(props))
    merged = f"{name}[{props_str}]" if props_str else name
    merged += nbt
    try:
        from mcbuilder.blocks import canonicalize
    except ImportError:
        return merged
    return canonicalize(merged)


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
    canonical block string, normalized via
    ``mcbuilder.blocks.canonicalize`` with a lazy import to avoid
    circular imports). Any other props on ``block`` are preserved.

    ``width > 1`` widens the run along the horizontal axis perpendicular
    to ``direction``, extending toward the positive side from ``start``:
    north/south runs widen along +X, east/west runs widen along +Z.
    """
    dir_key = direction.lower()
    if dir_key not in _DIRECTIONS:
        raise ValueError(
            f"stairs_run: invalid direction {direction!r}; "
            f"expected one of {sorted(_DIRECTIONS)}"
        )
    if length < 1:
        raise ValueError(f"stairs_run: length must be >= 1, got {length}")
    if width < 1:
        raise ValueError(f"stairs_run: width must be >= 1, got {width}")
    dx, dz = _DIRECTIONS[dir_key]
    facing = _OPPOSITE[dir_key]
    step_block = _merge_props(block, {"facing": facing, "half": "bottom"})
    # Perpendicular horizontal axis: runs along X widen along +Z and vice versa.
    px, pz = (0, 1) if dx != 0 else (1, 0)
    x0, y0, z0 = start
    for i in range(length):
        y = y0 + i
        for w in range(width):
            build.set(x0 + i * dx + w * px, y, z0 + i * dz + w * pz, step_block)


def pillar(build, base: tuple[int, int, int], height: int, block: str) -> None:
    """Vertical column of ``height`` blocks starting at ``base`` (inclusive).

    The ``block`` string is placed verbatim at every level — no props are
    added or altered. This is the deliberate contrast with ``stairs_run``:
    generic parts place strings verbatim (cf. plan §4.2: "no silent
    inference"), and only direction-implying parts compute properties.
    """
    if height < 1:
        raise ValueError(f"pillar: height must be >= 1, got {height}")
    x, y, z = base
    for i in range(height):
        build.set(x, y + i, z, block)


def railing(
    build,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    block: str,
) -> None:
    """Straight horizontal run of blocks from ``start`` to ``end`` inclusive.

    Must be axis-aligned (x or z constant, y constant across both points)
    else a ``ValueError`` is raised naming the problem.

    Typically used with fence blocks. Note for the agent: the exporter
    writes the bare block (``minecraft:oak_fence``) and the *game* resolves
    fence/wall connections at paste time — connections are runtime state,
    not stored blockstate data. So previews will show fences without
    connected arms; the in-game paste will show the correct connected
    shape. (Plan §4.3 / §4.4: the faithful renderer renders the first
    ``apply`` model and warns about approximate multipart blocks.)
    """
    x1, y1, z1 = start
    x2, y2, z2 = end
    if y1 != y2:
        raise ValueError(
            f"railing: start and end must share the same y level "
            f"(got y={y1} and y={y2})"
        )
    if x1 != x2 and z1 != z2:
        raise ValueError(
            f"railing: run must be axis-aligned (x or z constant); "
            f"got start=({x1}, {y1}, {z1}) end=({x2}, {y2}, {z2})"
        )
    dist = max(abs(x2 - x1), abs(z2 - z1))
    sx = 0 if x1 == x2 else (1 if x2 > x1 else -1)
    sz = 0 if z1 == z2 else (1 if z2 > z1 else -1)
    for i in range(dist + 1):
        build.set(x1 + i * sx, y1, z1 + i * sz, block)
