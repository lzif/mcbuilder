"""Block string parsing, canonicalization, and did-you-mean suggestions.

A block string is a namespaced name with optional blockstate properties
and optional NBT::

    minecraft:oak_stairs[facing=north,half=bottom]
    minecraft:chest{Items:[{Slot:0b,id:"minecraft:stone"}]}
    minecraft:furnace[facing=east]{BurnTime:200s}

``parse`` splits such a string into ``(name, props, nbt)`` and raises
``ValueError`` on anything structurally malformed. ``canonicalize``
produces the stable palette-key form stored in :class:`VoxelGrid`
(properties sorted alphabetically, NBT top-level keys sorted); it is
idempotent. ``suggest`` offers did-you-mean candidates for unknown names.

Notes on strictness: this module only checks *structure*. Whether the
name exists, whether a property is legal for the block, and whether NBT
values are well-typed is the validator's job (a different component).
"""

from __future__ import annotations

import difflib
import hashlib

from mcbuilder.errors import McbuilderError


def parse(block: str) -> tuple[str, dict[str, str], str | None]:
    """Split a block string into ``(name, properties, nbt)``.

    Returns ``(name, props_dict, nbt_string_or_None)``. The NBT string is
    returned verbatim (including braces); use :func:`canonicalize` for
    the normalized form.

    Raises ``ValueError`` on malformed input: empty string, empty name,
    unclosed/misordered brackets or braces, empty or malformed property
    list, duplicate property keys, unbalanced NBT.
    """
    if not isinstance(block, str) or not block:
        raise ValueError(f"malformed block string {block!r}: must be a non-empty string")

    # NBT must come last: find the first '{' and treat everything from
    # there as the NBT compound (this keeps '{Items:[...]}' intact).
    brace = block.find("{")
    head = block if brace == -1 else block[:brace]
    nbt: str | None = None
    if brace != -1:
        nbt = _check_compound(block[brace:])

    bracket = head.find("[")
    if bracket == -1:
        name, props = head, {}
    else:
        name = head[:bracket]
        rest = head[bracket:]
        if not rest.endswith("]"):
            raise ValueError(f"malformed block string {block!r}: unclosed '['")
        props = _parse_props(rest[1:-1], block)

    if not name:
        raise ValueError(f"malformed block string {block!r}: empty block name")
    if any(c in name for c in "[]{},") or any(c.isspace() for c in name):
        raise ValueError(f"malformed block string {block!r}: bad block name {name!r}")
    return name, props, nbt


def canonicalize(block: str) -> str:
    """Return the canonical palette-key form of a block string.

    Canonical form is ``name`` + ``[props sorted alphabetically]`` +
    ``{nbt with top-level keys sorted}``. NBT *values* are opaque and kept
    verbatim (only top-level ``key:value`` entries are reordered and their
    surrounding whitespace normalized).

    Idempotent: ``canonicalize(canonicalize(x)) == canonicalize(x)``.
    Raises ``ValueError`` on malformed input (see :func:`parse`).
    """
    name, props, nbt = parse(block)
    out = name
    if props:
        out += "[" + ",".join(f"{k}={props[k]}" for k in sorted(props)) + "]"
    if nbt is not None:
        out += _canonicalize_nbt(nbt)
    return out


def suggest(name: str, candidates: list[str], n: int = 3) -> list[str]:
    """Return up to ``n`` did-you-mean candidates for ``name``.

    Matching is done on the namespace-stripped name (``oak_stair`` still
    matches ``minecraft:oak_stairs``) via ``difflib.get_close_matches``,
    but the returned entries are the full candidate strings.
    """
    if n <= 0:
        return []
    plain = name.split(":", 1)[-1]
    table: dict[str, str] = {}
    plains: list[str] = []
    for cand in candidates:
        p = cand.split(":", 1)[-1]
        if p not in table:
            table[p] = cand
            plains.append(p)
    return [table[p] for p in difflib.get_close_matches(plain, plains, n=n)]


def _parse_props(inner: str, block: str) -> dict[str, str]:
    if not inner:
        raise ValueError(f"malformed block string {block!r}: empty property list '[]'")
    props: dict[str, str] = {}
    for item in _split_top_level(inner):
        key, sep, value = item.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or not value:
            raise ValueError(f"malformed block string {block!r}: bad property {item!r}")
        if any(c.isspace() for c in key):
            raise ValueError(f"malformed block string {block!r}: bad property key {key!r}")
        if key in props:
            raise ValueError(f"malformed block string {block!r}: duplicate property {key!r}")
        props[key] = value
    return props


def _check_compound(raw: str) -> str:
    """Validate that ``raw`` is exactly one balanced NBT compound; return it.

    Raises ``ValueError`` if braces/brackets are unbalanced, a quoted
    string is unterminated, or anything trails the closing brace (e.g.
    ``{a:1}[x=1]`` — properties must precede NBT).
    """
    depth_c = depth_s = 0
    quote: str | None = None
    closed_at: int | None = None
    i, n = 0, len(raw)
    while i < n:
        ch = raw[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "{":
            depth_c += 1
        elif ch == "}":
            depth_c -= 1
            if depth_c < 0:
                raise ValueError(f"malformed NBT {raw!r}: unbalanced '}}'")
            if depth_c == 0 and closed_at is None:
                closed_at = i
        elif ch == "[":
            depth_s += 1
        elif ch == "]":
            depth_s -= 1
            if depth_s < 0:
                raise ValueError(f"malformed NBT {raw!r}: unbalanced ']'")
        i += 1
    if quote is not None:
        raise ValueError(f"malformed NBT {raw!r}: unterminated string")
    if depth_c != 0 or depth_s != 0:
        raise ValueError(f"malformed NBT {raw!r}: unbalanced braces/brackets")
    if closed_at != n - 1:
        raise ValueError(f"malformed NBT {raw!r}: trailing characters after compound")
    return raw


def _canonicalize_nbt(raw: str) -> str:
    inner = raw[1:-1]
    if not inner.strip():
        return "{}"
    entries: list[tuple[str, str]] = []
    for part in _split_top_level(inner):
        if not part.strip():
            raise ValueError(f"malformed NBT {raw!r}: empty entry")
        key, value = _split_key_value(part, raw)
        if not key:
            raise ValueError(f"malformed NBT {raw!r}: empty key in {part!r}")
        entries.append((key, value))
    entries.sort(key=lambda kv: kv[0])
    return "{" + ",".join(f"{k}:{v}" for k, v in entries) + "}"


def _split_key_value(entry: str, raw: str) -> tuple[str, str]:
    """Split an NBT ``key:value`` entry at the first top-level colon."""
    depth_c = depth_s = 0
    quote: str | None = None
    i, n = 0, len(entry)
    while i < n:
        ch = entry[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "{":
            depth_c += 1
        elif ch == "}":
            depth_c -= 1
        elif ch == "[":
            depth_s += 1
        elif ch == "]":
            depth_s -= 1
        elif ch == ":" and depth_c == 0 and depth_s == 0:
            return entry[:i].strip(), entry[i + 1 :].strip()
        i += 1
    raise ValueError(f"malformed NBT {raw!r}: entry without ':' — {entry!r}")


def _split_top_level(s: str) -> list[str]:
    """Split on commas that are not nested inside ``{...}``/``[...]``/quotes."""
    parts: list[str] = []
    depth_c = depth_s = 0
    quote: str | None = None
    cur: list[str] = []
    i, n = 0, len(s)
    while i < n:
        ch = s[i]
        if quote is not None:
            cur.append(ch)
            if ch == "\\" and i + 1 < n:
                cur.append(s[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            cur.append(ch)
        elif ch == "{":
            depth_c += 1
            cur.append(ch)
        elif ch == "}":
            depth_c -= 1
            cur.append(ch)
        elif ch == "[":
            depth_s += 1
            cur.append(ch)
        elif ch == "]":
            depth_s -= 1
            cur.append(ch)
        elif ch == "," and depth_c == 0 and depth_s == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return parts


# ---------------------------------------------------------------------------
# material specs (finding 6)
# ---------------------------------------------------------------------------
# A material spec is ``str | Sequence[str | tuple[str, float]] |
# Callable[[int, int, int], str]``:
# - ``str``: one block, placed verbatim (the historical behavior).
# - sequence: weighted palette — bare strings weigh 1.0, ``(block, weight)``
#   pairs weigh ``weight``. The pick is a stable coordinate hash of
#   ``(seed, x, y, z)``: the same cell always resolves the same way no
#   matter the call order (unlike a shared RNG stream).
# - callable: ``f(x, y, z) -> str``, called per cell; the result is
#   canonicalized (``ValueError`` on malformed strings, like ``set``).


def _coord_pick(seed, entries: list[tuple[str, float]], x: int, y: int,
                z: int) -> str:
    """Deterministic weighted pick from ``entries`` for cell ``(x, y, z)``."""
    total = sum(w for _, w in entries)
    h = int(hashlib.sha256(
        f"{seed}\x00{x},{y},{z}".encode("utf-8")).hexdigest(), 16)
    r = (h % 1_000_000) / 1_000_000 * total
    acc = 0.0
    for block, w in entries:
        acc += w
        if r < acc:
            return block
    return entries[-1][0]  # float-rounding guard


def resolve_material(spec, x: int, y: int, z: int, seed=None) -> str:
    """Resolve a material spec to a canonical block string for one cell.

    ``seed`` salts the coordinate hash (``Build`` passes its own seed;
    pure ``mb.part.*`` factories take a ``seed`` kwarg, defaulting to
    ``None`` — deterministic either way, just fixed across seeds).
    """
    if isinstance(spec, str):
        return canonicalize(spec)
    if callable(spec):
        return canonicalize(spec(x, y, z))
    try:
        items = list(spec)
    except TypeError:
        raise McbuilderError(
            f"invalid material spec {spec!r}: expected a block string, "
            "a sequence of block strings / (block, weight) pairs, or a "
            "callable (x, y, z) -> str"
        )
    entries: list[tuple[str, float]] = []
    for e in items:
        if isinstance(e, str):
            entries.append((canonicalize(e), 1.0))
        elif (isinstance(e, (tuple, list)) and len(e) == 2
                and isinstance(e[0], str)):
            try:
                w = float(e[1])
            except (TypeError, ValueError):
                raise McbuilderError(
                    f"invalid palette weight {e[1]!r} for {e[0]!r}")
            if w < 0:
                raise McbuilderError(
                    f"negative palette weight {w} for {e[0]!r}")
            entries.append((canonicalize(e[0]), w))
        else:
            raise McbuilderError(
                f"invalid palette entry {e!r}: expected a block string or "
                "a (block, weight) pair")
    if not entries:
        raise McbuilderError("material palette is empty")
    if sum(w for _, w in entries) <= 0:
        raise McbuilderError("material palette weights sum to zero")
    return _coord_pick(seed, entries, x, y, z)
