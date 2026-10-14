"""Structure rotation semantics (PLAN §3, normative table).

Mirrors ``StructurePaster.rotateBlockData()`` (LostQoL, commit
``0f83d68`` — spot-checked against the Kotlin): the exact position and
blockstate transforms a structure paste applies for each
``StructureRotation``. mcbuilder uses this to verify designs rotate
cleanly (the v0.2 acceptance is "pastes correctly at all 4 rotations")
and so the direction-trusted preview tier shares one source of truth
with the server-side paster.

Rotations (clockwise viewed from above, matching Bukkit's
``StructureRotation``):

- ``NONE`` — identity
- ``CLOCKWISE_90`` — north→east
- ``CLOCKWISE_180`` — north→south
- ``COUNTERCLOCKWISE_90`` — north→west

Positions (footprint ``s``, 0-based cell coords):

- ``NONE``: ``(x, z)``
- ``CLOCKWISE_90``: ``(s - 1 - z, x)``
- ``CLOCKWISE_180``: ``(s - 1 - x, s - 1 - z)``
- ``COUNTERCLOCKWISE_90``: ``(z, s - 1 - x)``

Blockstates:

- ``facing``: horizontal facings cycle n→e→s→w (CW90),
  n→w→s→e (CCW90), n↔s / e↔w (180); ``up``/``down`` invariant.
- ``axis``: ``x``↔``z`` on 90° turns; ``y`` invariant; 180 is identity.
- sign/banner ``rotation`` (0–15 int): +4 / +8 / +12 (mod 16).
- cardinal connection keys (``north``/``east``/``south``/``west`` on
  fences, walls, panes, vines, mushroom blocks, …): the KEY names the
  direction, so the keys are permuted through the same facing maps
  (values untouched).
- compound ``orientation`` values (``"north_up"``, ``"east_down"``,
  …): the horizontal head is permuted; the rest is untouched.
- everything else (``half``, ``shape``, ``hinge``, ``open``,
  ``waterlogged``, slab ``type``, …) is invariant under rigid
  horizontal rotation.
"""

from __future__ import annotations

import re

from mcbuilder.blocks import canonicalize
from mcbuilder.errors import McbuilderError

__all__ = [
    "ROTATIONS",
    "mirror_blockstate",
    "rotate_blockstate",
    "rotate_position",
]

#: Valid rotation names (Bukkit ``StructureRotation`` order).
ROTATIONS = ("NONE", "CLOCKWISE_90", "CLOCKWISE_180", "COUNTERCLOCKWISE_90")

_FACING_CW90 = {"north": "east", "east": "south", "south": "west", "west": "north"}
_FACING_CCW90 = {v: k for k, v in _FACING_CW90.items()}
_FACING_180 = {"north": "south", "south": "north", "east": "west", "west": "east"}

_PROP_RE = re.compile(r"\[([^\]]*)\]")


def _check_rotation(rotation: str) -> str:
    if rotation not in ROTATIONS:
        raise McbuilderError(
            f"invalid rotation {rotation!r}; expected one of {list(ROTATIONS)}"
        )
    return rotation


def _rotate_point(x: int, z: int, ax: int, az: int,
                  rotation: str) -> tuple[int, int]:
    """Rotate point ``(x, z)`` about anchor ``(ax, az)`` (cell-corner frame).

    Same clockwise-from-above convention as :func:`rotate_position`, but
    for arbitrary integer anchors instead of square footprints. ``NONE``
    is the identity.
    """
    _check_rotation(rotation)
    rx, rz = x - ax, z - az
    if rotation == "CLOCKWISE_90":
        rx, rz = -rz, rx
    elif rotation == "COUNTERCLOCKWISE_90":
        rx, rz = rz, -rx
    elif rotation == "CLOCKWISE_180":
        rx, rz = -rx, -rz
    return ax + rx, az + rz


def rotate_position(
    x: int, z: int, size: int, rotation: str
) -> tuple[int, int]:
    """Rotate a footprint cell ``(x, z)`` for a square footprint of ``size``.

    Y is untouched (rotations are horizontal). Matches the paster's
    position transform exactly.
    """
    _check_rotation(rotation)
    if rotation == "NONE":
        return (x, z)
    if rotation == "CLOCKWISE_90":
        return (size - 1 - z, x)
    if rotation == "CLOCKWISE_180":
        return (size - 1 - x, size - 1 - z)
    return (z, size - 1 - x)  # COUNTERCLOCKWISE_90


def _facing_map(rotation: str) -> dict[str, str] | None:
    if rotation == "CLOCKWISE_90":
        return _FACING_CW90
    if rotation == "COUNTERCLOCKWISE_90":
        return _FACING_CCW90
    if rotation == "CLOCKWISE_180":
        return _FACING_180
    return None


def _remap_props(props: dict[str, str], rotation: str) -> dict[str, str]:
    out = dict(props)
    fmap = _facing_map(rotation)
    if fmap is not None:
        facing = out.get("facing")
        if facing in fmap:
            out["facing"] = fmap[facing]
        # up/down and unknown facings pass through untouched.
        # Cardinal connection keys: the KEY names the direction — permute
        # the keys through the facing map (collect-then-assign: the map is
        # a permutation, so in-place reassignment would double-remap).
        remapped: dict[str, str] = {}
        for key in ("north", "east", "south", "west"):
            if key in out:
                remapped[fmap[key]] = out[key]
        for key in ("north", "east", "south", "west"):
            out.pop(key, None)
        out.update(remapped)
        # Compound orientation values ("north_up", "east_down", ...):
        # remap the horizontal head, keep the rest.
        ori = out.get("orientation")
        if isinstance(ori, str):
            head, sep, tail = ori.partition("_")
            if head in fmap:
                out["orientation"] = fmap[head] + sep + tail
    if rotation in ("CLOCKWISE_90", "COUNTERCLOCKWISE_90"):
        axis = out.get("axis")
        if axis == "x":
            out["axis"] = "z"
        elif axis == "z":
            out["axis"] = "x"
    rot = out.get("rotation")
    if rot is not None and rot.lstrip("-").isdigit():
        shift = {"CLOCKWISE_90": 4, "CLOCKWISE_180": 8,
                 "COUNTERCLOCKWISE_90": 12}[rotation]
        out["rotation"] = str((int(rot) + shift) % 16)
    return out


def _split_blockstate_props(canonical: str):
    """Split canonical -> (name, props dict, nbt). Shared by the transforms."""
    nbt = ""
    head = canonical
    brace = head.find("{")
    if brace != -1:
        nbt = head[brace:]
        head = head[:brace]
    m = _PROP_RE.search(head)
    props: dict[str, str] = {}
    name = head
    if m:
        name = head[: m.start()]
        for item in m.group(1).split(","):
            item = item.strip()
            if not item:
                continue
            key, _, value = item.partition("=")
            props[key.strip()] = value.strip()
    return name, props, nbt


def _join_blockstate(name: str, props: dict[str, str], nbt: str) -> str:
    props_str = ",".join(f"{k}={props[k]}" for k in sorted(props))
    return canonicalize(f"{name}[{props_str}]{nbt}" if props_str else name + nbt)


def rotate_blockstate(canonical: str, rotation: str) -> str:
    """Rotate one canonical block string per the §3 blockstate table.

    The input must already be canonical (as produced by
    :func:`mcbuilder.blocks.canonicalize`); the output is canonical too.
    Non-directional blocks pass through unchanged (but still normalized).
    """
    _check_rotation(rotation)
    if rotation == "NONE":
        return canonicalize(canonical)
    name, props, nbt = _split_blockstate_props(canonical)
    if not props:
        return canonicalize(canonical)  # no props: nothing to rotate
    return _join_blockstate(name, _remap_props(props, rotation), nbt)


_MIRROR_FACING = {
    "x": {"east": "west", "west": "east"},
    "z": {"north": "south", "south": "north"},
}


def mirror_blockstate(canonical: str, axis: str) -> str:
    """Mirror one canonical block string across the ``axis`` plane.

    ``axis="x"`` maps ``x → -x`` (facing east↔west); ``axis="z"`` maps
    ``z → -z`` (facing north↔south). Cardinal connection keys and the
    horizontal head of compound ``orientation`` values are swapped the
    same way. ``up``/``down`` facings, ``axis`` props, sign ``rotation``
    ints and door ``hinge`` pass through unchanged — known v0
    limitations, documented here rather than guessed.
    """
    if axis not in ("x", "z"):
        raise McbuilderError(
            f"invalid mirror axis {axis!r}; expected 'x' or 'z'"
        )
    name, props, nbt = _split_blockstate_props(canonical)
    if not props:
        return canonicalize(canonical)
    swap = _MIRROR_FACING[axis]
    out = dict(props)
    facing = out.get("facing")
    if facing in swap:
        out["facing"] = swap[facing]
    remapped: dict[str, str] = {}
    for key in ("north", "east", "south", "west"):
        if key in out:
            remapped[swap.get(key, key)] = out[key]
    for key in ("north", "east", "south", "west"):
        out.pop(key, None)
    out.update(remapped)
    ori = out.get("orientation")
    if isinstance(ori, str):
        head, sep, tail = ori.partition("_")
        if head in swap:
            out["orientation"] = swap[head] + sep + tail
    return _join_blockstate(name, out, nbt)
