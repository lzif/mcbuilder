"""Tests for the vanilla structure-block ``.nbt`` exporter.

The compatibility test mirrors the acceptance rules of the known consumer
(LostQoL's ``StructureNbt`` parser): root compound with ``palette`` /
``blocks`` / ``size``, palette entries carrying ``Name`` (+ optional
``Properties``), block entries with ``pos``/``state``, air skipped.
"""

import json

import nbtlib
import pytest

from mcbuilder import build as build_mod
from mcbuilder import export_nbt as export_nbt_mod
from mcbuilder import voxels as voxels_mod


def _sample_grid():
    """Small build: directional stair, carved air, plain blocks."""
    b = build_mod.Build(seed=7)
    with b:
        b.box((0, 0, 0), (2, 1, 2), "minecraft:stone")
        b.set(1, 2, 1, "minecraft:oak_stairs[facing=north,half=bottom]")
        b.set(0, 0, 0, "minecraft:air")  # carved air inside the box
    return b.grid


def _read_back(path):
    """Return ``(root, palette, cells)`` from a written .nbt file.

    ``palette`` is a list of ``(name, props_dict)``; ``cells`` maps
    ``(x, y, z)`` to the canonical-ish blockstate string.
    """
    f = nbtlib.load(str(path), gzipped=True)
    pal = []
    for e in f["palette"]:
        name = str(e["Name"])
        props = e.get("Properties")
        pal.append(
            (name, {str(k): str(v) for k, v in props.items()} if props else {})
        )
    cells = {}
    for be in f["blocks"]:
        pos = tuple(int(v) for v in be["pos"])
        name, pd = pal[int(be["state"])]
        s = name
        if pd:
            s += "[" + ",".join(f"{k}={pd[k]}" for k in sorted(pd)) + "]"
        cells[pos] = s
    return f, pal, cells


def _expected_cells(grid):
    arr, palette, _prov = grid.to_dense()
    expected = {}
    sx, sy, sz = (int(d) for d in arr.shape)
    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                idx = int(arr[x, y, z])
                if idx == voxels_mod.UNSET:
                    continue
                name = palette[idx]
                if name == voxels_mod.AIR:
                    continue
                expected[(x, y, z)] = name
    return expected


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------

def test_roundtrip_blockstate_equality(tmp_path):
    """Write -> read back -> blockstate-equality per cell (not index-equality)."""
    grid = _sample_grid()
    out = tmp_path / "hut.nbt"
    warnings = export_nbt_mod.write_structure_nbt(
        grid, out, data_version=4189, include_air=False
    )
    assert warnings == []
    _root, _pal, cells = _read_back(out)
    assert cells == _expected_cells(grid)
    # directional block survived the round trip with properties intact
    assert cells[(1, 2, 1)] == "minecraft:oak_stairs[facing=north,half=bottom]"


def test_structurenbt_compatibility(tmp_path):
    """The file parses under the same rules as LostQoL's StructureNbt."""
    grid = _sample_grid()
    out = tmp_path / "hut.nbt"
    export_nbt_mod.write_structure_nbt(grid, out, data_version=4903)

    raw = out.read_bytes()
    assert raw[:2] == b"\x1f\x8b"  # gzipped

    f = nbtlib.load(str(out), gzipped=True)
    # root compound with the three fields the parser reads (+ DataVersion)
    assert int(f["DataVersion"]) == 4903
    size = [int(v) for v in f["size"]]
    assert size == [3, 3, 3]
    palette = list(f["palette"])
    blocks = list(f["blocks"])
    assert palette and blocks

    air_states = set()
    for i, e in enumerate(palette):
        # entry["Name"] is a string; Properties, when present, is a
        # compound of strings (never numbers/booleans)
        assert isinstance(str(e["Name"]), str) and str(e["Name"])
        props = e.get("Properties")
        if props is not None:
            for k, v in props.items():
                assert isinstance(str(k), str)
                assert isinstance(str(v), str)
        if str(e["Name"]) == voxels_mod.AIR:
            air_states.add(i)

    for be in blocks:
        # pos: list of exactly 3 ints inside the size bounds (the parser
        # accepts List or IntArray; we write List like vanilla does)
        pos = [int(v) for v in be["pos"]]
        assert len(pos) == 3
        assert all(0 <= p < s for p, s in zip(pos, size))
        # state: palette index in range
        state = int(be["state"])
        assert 0 <= state < len(palette)
        # air skipped: no block entry may reference an air palette entry
        assert state not in air_states

    # every non-air cell from the grid is present exactly once
    assert len(blocks) == len(_expected_cells(grid))


def test_include_air_writes_unset_cells(tmp_path):
    grid = _sample_grid()
    out = tmp_path / "hut.nbt"
    export_nbt_mod.write_structure_nbt(grid, out, data_version=4189,
                                       include_air=True)
    _root, _pal, cells = _read_back(out)
    # every bbox cell is present now (3*3*3), unset ones as air
    assert len(cells) == 27
    assert voxels_mod.AIR in cells.values()


# ---------------------------------------------------------------------------
# DataVersion resolution
# ---------------------------------------------------------------------------

def test_data_version_table():
    assert export_nbt_mod.resolve_data_version("26.2") == 4903
    assert export_nbt_mod.resolve_data_version("1.21.4") == 4189


def test_data_version_prefers_version_json(tmp_path):
    (tmp_path / "version.json").write_text(
        json.dumps({"world_version": 9999}), encoding="utf-8"
    )
    assert export_nbt_mod.resolve_data_version("26.2", tmp_path) == 9999


def test_data_version_unknown_raises():
    with pytest.raises(export_nbt_mod.ExportError, match="unknown DataVersion"):
        export_nbt_mod.resolve_data_version("99.99")


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

def test_determinism(tmp_path):
    """Same grid -> byte-identical file."""
    grid = _sample_grid()
    a, b = tmp_path / "a.nbt", tmp_path / "b.nbt"
    export_nbt_mod.write_structure_nbt(grid, a, data_version=4189)
    export_nbt_mod.write_structure_nbt(grid, b, data_version=4189)
    assert a.read_bytes() == b.read_bytes()


def test_empty_grid_raises(tmp_path):
    b = build_mod.Build(seed=1)
    with pytest.raises(export_nbt_mod.ExportError, match="empty"):
        export_nbt_mod.write_structure_nbt(
            b.grid, tmp_path / "empty.nbt", data_version=4189
        )


def test_block_entity_nbt_stripped_with_warning(tmp_path):
    b = build_mod.Build(seed=3)
    with b:
        b.set(0, 0, 0, "minecraft:chest{Items:[]}")
    out = tmp_path / "chest.nbt"
    warnings = export_nbt_mod.write_structure_nbt(
        b.grid, out, data_version=4189
    )
    assert len(warnings) == 1 and "block-entity NBT" in warnings[0]
    f = nbtlib.load(str(out), gzipped=True)
    assert str(f["palette"][0]["Name"]) == "minecraft:chest"
    assert "Properties" not in f["palette"][0]
    # the NBT payload made it nowhere into the file
    assert b"Items" not in out.read_bytes()
