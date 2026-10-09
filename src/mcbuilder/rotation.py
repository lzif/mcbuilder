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


def _remap_props(props: dict[str, str], rotation: str) -> dict[str, str]:
    out = dict(props)
    facing = out.get("facing")
    if facing in _FACING_CW90:
        if rotation == "CLOCKWISE_90":
            out["facing"] = _FACING_CW90[facing]
        elif rotation == "COUNTERCLOCKWISE_90":
            out["facing"] = _FACING_CCW90[facing]
        elif rotation == "CLOCKWISE_180":
            out["facing"] = _FACING_180[facing]
    # up/down and unknown facings pass through untouched.
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


def rotate_blockstate(canonical: str, rotation: str) -> str:
    """Rotate one canonical block string per the §3 blockstate table.

    The input must already be canonical (as produced by
    :func:`mcbuilder.blocks.canonicalize`); the output is canonical too.
    Non-directional blocks pass through unchanged (but still normalized).
    """
    _check_rotation(rotation)
    if rotation == "NONE":
        return canonicalize(canonical)
    nbt = ""
    head = canonical
    brace = head.find("{")
    if brace != -1:
        nbt = head[brace:]
        head = head[:brace]
    m = _PROP_RE.search(head)
    if not m:
        return canonicalize(canonical)  # no props: nothing to rotate
    props: dict[str, str] = {}
    for item in m.group(1).split(","):
        item = item.strip()
        if not item:
            continue
        key, _, value = item.partition("=")
        props[key.strip()] = value.strip()
    remapped = _remap_props(props, rotation)
    name = head[: m.start()]
    props_str = ",".join(f"{k}={remapped[k]}" for k in sorted(remapped))
    return canonicalize(f"{name}[{props_str}]{nbt}" if props_str else name + nbt)
