"""Vanilla structure-block ``.nbt`` export (gzipped NBT serializer).

Writes the voxel grid in the same format a vanilla structure block saves:
a gzipped root compound with ``DataVersion``, ``size``, ``palette`` and
``blocks``. ``entities`` is written as an empty list — block entities and
entities are out of scope (the validator only syntax-checks block-entity
NBT, and the known consumer can't read them either).

``pos`` and ``size`` are TAG_List of TAG_Int (never TAG_Int_Array, which
``StructureManager.loadStructure`` and most parsers reject). The file loads
in a structure block, Litematica and server-side structure pasters.

Coordinate mapping: ``pos`` is ``[x, y, z]`` offsets from the bbox
minimum, ``size`` is ``[sx, sy, sz]`` — matching ``VoxelGrid.to_dense``,
whose array axis 0/1/2 is x/y/z.

Air handling (``air``):

- ``"none"`` (default): neither unset cells nor carved-air
  cells appear in ``blocks`` (air may still sit in the palette,
  unreferenced — vanilla-faithful). Pasting leaves whatever was there.
- ``"explicit"``: only cells explicitly set to ``minecraft:air`` are
  written; unset cells stay structure-void. Use this for builds that must
  displace the world *inside* the structure without touching what's
  *around* it — e.g. an underwater base whose interior air pocket must
  push out ocean water while the surrounding ocean stays wet.
- ``"all"``: every cell in the bbox is written; unset cells
  become air (clears the whole bounding box on paste).

Determinism: palette order follows grid insertion order, ``blocks`` are
sorted by ``(x, y, z)``, NBT compounds keep insertion order, and the gzip
wrapper is normalized (``mtime=0``, no embedded filename) — the same grid
always yields byte-identical output.
"""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path

from nbtlib import Compound, File, Int, List, String

from mcbuilder import blocks as blocks_mod
from mcbuilder import voxels as voxels_mod
from mcbuilder.errors import McbuilderError

__all__ = [
    "ExportError",
    "DATA_VERSIONS",
    "resolve_data_version",
    "write_structure_nbt",
]


class ExportError(McbuilderError):
    """Raised when a structure cannot be exported."""


# DataVersion per release, sourced from https://minecraft.wiki/w/Data_version
# (verified 2026-10-09). Fallback only: ``assets fetch`` extracts the client
# jar's root ``version.json`` (field ``world_version`` — verified against the
# real 26.2 client jar), which always wins when present.
DATA_VERSIONS = {
    "26.2": 4903,
    "26.1": 4786,
    "1.21.11": 4671,
    "1.21.4": 4189,
    "1.21.1": 3955,
}


def resolve_data_version(mc_version: str, version_dir: Path | str | None = None) -> int:
    """Return the integer DataVersion for a pinned MC version.

    Precedence: ``<version_dir>/version.json`` (``world_version`` field,
    extracted by ``assets fetch`` — authoritative) over the
    :data:`DATA_VERSIONS` table. Raises :class:`ExportError` when neither
    knows the version, with an actionable message.
    """
    if version_dir is not None:
        vf = Path(version_dir) / "version.json"
        if vf.is_file():
            try:
                data = json.loads(vf.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and isinstance(data.get("world_version"), int):
                return data["world_version"]
    try:
        return DATA_VERSIONS[mc_version]
    except KeyError:
        raise ExportError(
            f"unknown DataVersion for MC version {mc_version!r}: run "
            f"`mcbuild assets fetch --version {mc_version}` first so the "
            "client jar's version.json can supply it"
        ) from None


def _palette_entry(canonical: str) -> tuple[Compound, str | None]:
    """Convert one canonical block string to an NBT palette entry.

    Returns ``(entry, warning_or_None)``. Block-entity NBT (``{...}``) is
    stripped — neither the plugin parser nor this format's ``blocks``
    list can carry it — and reported so the caller can warn.
    """
    name, props, nbt = blocks_mod.parse(canonical)
    warning = None
    if nbt is not None:
        warning = (
            f"palette entry {canonical!r} carries block-entity NBT which "
            ".nbt export drops (no block_entities list is written)"
        )
    entry = Compound({"Name": String(name)})
    if props:
        entry["Properties"] = Compound({k: String(v) for k, v in sorted(props.items())})
    return entry, warning


AIR_MODES = ("none", "explicit", "all")


def write_structure_nbt(
    grid,
    path: Path | str,
    *,
    data_version: int,
    air: str = "none",
) -> list[str]:
    """Write ``grid`` as a gzipped vanilla structure ``.nbt`` file.

    ``air``: ``"none"``, ``"explicit"`` or ``"all"``; see the module docstring.

    Returns a list of warning strings (block-entity NBT dropped, ...).
    Raises :class:`ExportError` on an empty grid.
    """
    if air not in AIR_MODES:
        raise ExportError(f"air must be one of {AIR_MODES}, got {air!r}")
    air_mode = air
    arr, palette, _provenance = grid.to_dense()
    if arr.size == 0:
        raise ExportError("build is empty — nothing to export")

    warnings: list[str] = []
    nbt_palette: list[Compound] = []
    air_idx: int | None = None
    for i, canonical in enumerate(palette):
        entry, warning = _palette_entry(canonical)
        if warning is not None:
            warnings.append(warning)
        if str(entry["Name"]) == voxels_mod.AIR:
            air_idx = i
        nbt_palette.append(entry)

    if air_mode == "all" and air_idx is None:
        # No air was ever placed; the format still needs an air entry for
        # the explicitly-written unset cells below.
        air_idx = len(nbt_palette)
        nbt_palette.append(Compound({"Name": String(voxels_mod.AIR)}))

    sx, sy, sz = (int(d) for d in arr.shape)
    block_tags: list[Compound] = []
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                idx = int(arr[x, y, z])
                if idx == voxels_mod.UNSET:
                    if air_mode != "all":
                        continue
                    idx = air_idx  # set above when air_mode is "all"
                elif air_mode == "none" and idx == air_idx:
                    continue
                block_tags.append(
                    Compound(
                        {
                            "pos": List([Int(x), Int(y), Int(z)]),
                            "state": Int(idx),
                        }
                    )
                )

    root = Compound(
        {
            "DataVersion": Int(data_version),
            "size": List([Int(sx), Int(sy), Int(sz)]),
            "palette": List(nbt_palette),
            "blocks": List(block_tags),
            # Entities and block entities are out of scope (see module doc).
            "entities": List[Compound]([]),
        }
    )
    out = Path(path)
    if out.parent != Path("."):
        out.parent.mkdir(parents=True, exist_ok=True)
    # Normalized gzip wrapper (mtime=0, no embedded filename): nbtlib's
    # File.save would embed both, breaking byte-determinism.
    buf = io.BytesIO()
    File(root, root_name="").write(buf)
    with open(out, "wb") as f:
        with gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
            gz.write(buf.getvalue())
    return warnings
