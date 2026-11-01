"""Tests for `mcbuild import`: structure .nbt -> builder script."""

import runpy

import pytest

import mcbuilder as mb
from mcbuilder import export_nbt
from mcbuilder.cli import main
from mcbuilder.importer import StructureImportError, _merge_boxes, read_structure, to_script


def _sample_build():
    b = mb.Build(seed=3)
    with b:
        b.box((0, 0, 0), (4, 0, 3), "minecraft:stone_bricks")
        b.walls((0, 1, 0), (4, 3, 3), ["minecraft:oak_planks", "minecraft:spruce_planks"])
        b.roof_gable((-1, 4, -1), (5, 4, 4), "minecraft:oak_stairs", ridge="x")
        b.set(2, 1, 0, "minecraft:air")
    return b


def _write_nbt(build, path, air="none"):
    export_nbt.write_structure_nbt(build.grid, path, data_version=4903, air=air)
    return path


def test_round_trip_is_exact(tmp_path):
    original = read_structure(_write_nbt(_sample_build(), tmp_path / "hut.nbt"))
    script = tmp_path / "hut_imported.py"
    script.write_text(to_script(original))
    rebuilt = runpy.run_path(str(script))["BUILD"]
    again = read_structure(_write_nbt(rebuilt, tmp_path / "again.nbt"))
    assert again.blocks == original.blocks
    assert len(original.blocks) > 50


def test_script_merges_runs_and_names_states(tmp_path):
    text = to_script(read_structure(_write_nbt(_sample_build(), tmp_path / "hut.nbt")))
    assert 'STONE_BRICKS = "minecraft:stone_bricks"' in text
    assert "OAK_STAIRS_N_BOTTOM" in text
    # floor shifted by the 1-block roof overhang; whole floor in one call
    assert "BUILD.box((1, 0, 1), (5, 0, 4), STONE_BRICKS)" in text
    assert "# --- layer y = 0 ---" in text
    assert "size: 7 x 7 x 6" in text


def test_air_dropped_unless_kept(tmp_path):
    path = _write_nbt(_sample_build(), tmp_path / "hut.nbt", air="explicit")
    assert "minecraft:air" not in read_structure(path).blocks.values()
    kept = read_structure(path, keep_air=True).blocks
    assert kept[(3, 1, 1)] == "minecraft:air"  # (2,1,0) shifted by the roof overhang


def test_merge_boxes_covers_exactly():
    cells = {(x, y, z) for x in range(3) for y in range(2) for z in range(2)} | {(5, 0, 0)}
    boxes = _merge_boxes(cells)
    covered = {
        (x, y, z)
        for (x0, y0, z0), (x1, y1, z1) in boxes
        for x in range(x0, x1 + 1)
        for y in range(y0, y1 + 1)
        for z in range(z0, z1 + 1)
    }
    assert covered == cells and len(boxes) == 2


def test_rejects_non_structure(tmp_path):
    bad = tmp_path / "x.nbt"
    bad.write_bytes(b"not nbt")
    with pytest.raises(StructureImportError):
        read_structure(bad)


def test_cli_import(tmp_path, capsys):
    path = _write_nbt(_sample_build(), tmp_path / "hut.nbt")
    assert main(["import", str(path)]) == 0
    assert (tmp_path / "hut.py").is_file()
    assert "top block types" in capsys.readouterr().out
    assert main(["import", str(path)]) == 1  # refuses to overwrite
    assert main(["import", str(path), "--force"]) == 0
