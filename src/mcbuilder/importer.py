"""Import an existing build: a structure-block ``.nbt`` → a builder script.

:func:`read_structure` loads a vanilla structure ``.nbt`` (the format a
structure block saves; convert ``.schem``/``.litematic`` to it first) into a
``{(x, y, z): block_string}`` dict (air dropped unless asked for).
:func:`to_script` turns that into a readable mcbuilder script: one named
constant per block state, runs of the same block merged into ``box`` calls,
grouped by layer, with a summary header (size, block counts) for analysis.

Block-entity data (chest contents, sign text) and entities are not carried
over; the header says how many were dropped.
"""

from __future__ import annotations

import keyword
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import nbtlib

from mcbuilder.blocks import canonicalize
from mcbuilder.errors import McbuilderError

__all__ = ["Structure", "read_structure", "to_script"]

AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
SKIP_BLOCKS = {"minecraft:structure_void"}


class StructureImportError(McbuilderError):
    """The file isn't a structure this importer understands."""


@dataclass
class Structure:
    """Blocks read from a file, plus what could not be carried over."""

    blocks: dict[tuple[int, int, int], str]
    source: str
    data_version: int | None = None
    dropped_block_entities: int = 0
    dropped_entities: int = 0
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------


def _state(name, props) -> str:
    name = str(name)
    if ":" not in name:
        name = "minecraft:" + name
    if props:
        inner = ",".join(f"{k}={props[k]}" for k in sorted(props))
        return canonicalize(f"{name}[{inner}]")
    return canonicalize(name)


def _palette_compound(entry) -> str:
    props = {str(k): str(v) for k, v in (entry.get("Properties") or {}).items()}
    return _state(entry["Name"], props)


def _read_nbt(root) -> Structure:
    palette = root.get("palette")
    if palette is None and root.get("palettes"):
        palette = root["palettes"][0]  # random-variant structures: first variant
    if palette is None or "blocks" not in root:
        raise StructureImportError("not a structure .nbt (no palette/blocks)")
    states = [_palette_compound(p) for p in palette]
    blocks, dropped = {}, 0
    for b in root["blocks"]:
        x, y, z = (int(v) for v in b["pos"])
        blocks[(x, y, z)] = states[int(b["state"])]
        if "nbt" in b:
            dropped += 1
    return Structure(
        blocks,
        "",
        data_version=int(root["DataVersion"]) if "DataVersion" in root else None,
        dropped_block_entities=dropped,
        dropped_entities=len(root.get("entities") or []),
    )


def read_structure(path: str | Path, *, keep_air: bool = False) -> Structure:
    """Read a structure-block ``.nbt`` file.

    Coordinates are shifted so the smallest x, y and z are 0. Air is
    dropped unless ``keep_air`` (then it comes back as ``minecraft:air``);
    ``structure_void`` is always dropped.
    """
    path = Path(path)
    try:
        root = nbtlib.load(str(path))
    except Exception as e:  # noqa: BLE001 - any parse failure gets one clean message
        raise StructureImportError(f"{path.name}: not a readable NBT file ({e})") from None
    root = getattr(root, "root", root)
    if "blocks" not in root:
        raise StructureImportError(
            f"{path.name}: not a structure .nbt (convert .schem/.litematic to .nbt first)"
        )
    s = _read_nbt(root)
    out = {}
    for p, b in s.blocks.items():
        name = b.split("[", 1)[0]
        if name in SKIP_BLOCKS:
            continue
        if name in AIR_BLOCKS:
            if keep_air:
                out[p] = "minecraft:air"
            continue
        out[p] = b
    if out:
        mins = [min(p[i] for p in out) for i in range(3)]
        out = {(x - mins[0], y - mins[1], z - mins[2]): b for (x, y, z), b in out.items()}
    s.blocks = out
    s.source = path.name
    return s


# ---------------------------------------------------------------------------
# script writer
# ---------------------------------------------------------------------------


def _merge_boxes(cells: set[tuple[int, int, int]]) -> list[tuple[tuple, tuple]]:
    """Greedy cover of ``cells`` with axis-aligned boxes (no overlaps)."""
    left = set(cells)
    boxes = []
    for x0, y0, z0 in sorted(cells, key=lambda p: (p[1], p[2], p[0])):
        if (x0, y0, z0) not in left:
            continue
        x1 = x0
        while (x1 + 1, y0, z0) in left:
            x1 += 1
        z1 = z0
        while all((x, y0, z1 + 1) in left for x in range(x0, x1 + 1)):
            z1 += 1
        y1 = y0
        while all((x, y1 + 1, z) in left for x in range(x0, x1 + 1) for z in range(z0, z1 + 1)):
            y1 += 1
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                for z in range(z0, z1 + 1):
                    left.discard((x, y, z))
        boxes.append(((x0, y0, z0), (x1, y1, z1)))
    return boxes


_ABBREV = {"north": "N", "south": "S", "east": "E", "west": "W", "true": "T", "false": "F"}


def _const_name(block: str, taken: set[str]) -> str:
    base, _, props = block.partition("[")
    name = base.split(":", 1)[1].upper()
    parts = []
    for kv in props.rstrip("]").split(","):
        if "=" in kv:
            k, v = kv.split("=", 1)
            if k == "waterlogged" and v == "false":
                continue
            parts.append(_ABBREV.get(v, v).upper())
    cand = re.sub(r"[^A-Z0-9_]", "_", "_".join([name, *parts]))
    if cand[0].isdigit() or keyword.iskeyword(cand.lower()):
        cand = "B_" + cand
    out, n = cand, 2
    while out in taken:
        out, n = f"{cand}_{n}", n + 1
    taken.add(out)
    return out


def summary(structure: Structure, top: int = 25) -> list[str]:
    """Human-readable analysis lines: size, block counts, block families."""
    blocks = structure.blocks
    if not blocks:
        return ["empty structure"]
    dims = [max(p[i] for p in blocks) + 1 for i in range(3)]
    by_name = Counter(b.split("[", 1)[0] for b in blocks.values() if b != "minecraft:air")
    solid = sum(by_name.values())
    lines = [
        f"source: {structure.source}"
        + (f" (DataVersion {structure.data_version})" if structure.data_version else ""),
        f"size: {dims[0]} x {dims[1]} x {dims[2]} (x * y * z), {solid} blocks, "
        f"{len(by_name)} block types, {len(set(blocks.values()))} block states",
    ]
    if structure.dropped_block_entities or structure.dropped_entities:
        lines.append(
            f"not imported: {structure.dropped_block_entities} block-entity data "
            f"(chest contents, signs...), {structure.dropped_entities} entities"
        )
    lines.append("")
    lines.append(f"top block types (of {len(by_name)}):")
    for name, n in by_name.most_common(top):
        lines.append(f"  {n:>6}  {100 * n / solid:5.1f}%  {name.split(':', 1)[1]}")
    per_layer = Counter(p[1] for p, b in blocks.items() if b != "minecraft:air")
    lines.append("")
    lines.append(
        "blocks per layer (y): " + ", ".join(f"{y}:{per_layer[y]}" for y in range(dims[1]))
    )
    return lines


def to_script(structure: Structure, *, seed: int = 0) -> str:
    """A runnable mcbuilder script that rebuilds ``structure`` exactly."""
    blocks = structure.blocks
    by_block: dict[str, set] = defaultdict(set)
    for p, b in blocks.items():
        by_block[b].add(p)
    counts = Counter(blocks.values())
    taken: set[str] = set()
    names = {b: _const_name(b, taken) for b in sorted(counts, key=lambda b: (-counts[b], b))}

    calls: list[tuple[int, int, int, str]] = []
    for block, cells in by_block.items():
        for c1, c2 in _merge_boxes(cells):
            if c1 == c2:
                code = f"BUILD.set({c1[0]}, {c1[1]}, {c1[2]}, {names[block]})"
            else:
                code = f"BUILD.box({c1}, {c2}, {names[block]})"
            calls.append((c1[1], c1[2], c1[0], code))
    calls.sort()

    out = ['"""Imported from ' + structure.source + " by `mcbuild import`.", ""]
    out += summary(structure)
    out += [
        "",
        "Coordinates: x east, y up, z south; (0, 0, 0) is the north-west bottom corner.",
        '"""',
        "",
        "import mcbuilder as mb",
        "",
        f'BUILD = mb.Build(seed={seed}, views="iso;az200_el025;top")',
        "",
        "# block states, most used first",
    ]
    out += [f'{names[b]} = "{b}"  # {counts[b]}' for b in names]
    out += ["", "with BUILD:"]
    if not calls:
        out.append("    pass")
    layer = None
    for y, _z, _x, code in calls:
        if y != layer:
            out += ["", f"    # --- layer y = {y} ---"]
            layer = y
        out.append("    " + code)
    return "\n".join(out) + "\n"
