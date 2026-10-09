"""Tests for mcbuilder.voxels: VoxelGrid, palette interning, bounds, errors."""

import numpy as np
import pytest

from mcbuilder.errors import McbuilderError
from mcbuilder.voxels import AIR, UNSET, GridBoundsError, VoxelGrid


def test_place_and_to_dense():
    g = VoxelGrid()
    g.place(1, 2, 3, "minecraft:stone", ("script.py", 10))
    arr, palette, prov = g.to_dense()
    assert arr.dtype == np.int32
    assert arr.shape == (1, 1, 1)
    assert arr[0, 0, 0] == 0
    assert palette == ["minecraft:stone"]
    assert prov == {0: ("script.py", 10)}


def test_palette_interning_last_write_wins():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", ("a.py", 1))
    g.place(0, 0, 0, "minecraft:dirt", ("a.py", 2))
    g.place(5, 5, 5, "minecraft:stone", ("a.py", 3))
    arr, palette, _ = g.to_dense()
    assert palette == ["minecraft:stone", "minecraft:dirt"]
    # cell (0,0,0) now dirt (index 1); stone reused at (5,5,5) (index 0)
    assert arr[0, 0, 0] == 1
    assert arr[5, 5, 5] == 0


def test_provenance_first_placement_wins_per_palette_index():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", ("a.py", 1))
    g.place(9, 9, 9, "minecraft:stone", ("a.py", 99))
    _, _, prov = g.to_dense()
    assert prov == {0: ("a.py", 1)}


def test_provenance_none_not_recorded_but_later_known_wins():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", None)
    g.place(1, 0, 0, "minecraft:stone", ("a.py", 5))
    _, _, prov = g.to_dense()
    assert prov == {0: ("a.py", 5)}


def test_bounds_inclusive():
    g = VoxelGrid()
    assert g.bounds() is None
    g.place(3, 1, -2, "minecraft:stone", None)
    g.place(-1, 7, 4, "minecraft:dirt", None)
    assert g.bounds() == ((-1, 1, -2), (3, 7, 4))


def test_bounds_ignores_explicit_air():
    g = VoxelGrid()
    g.place(0, 0, 0, AIR, None)
    assert g.bounds() is None
    assert g.count_non_air() == 0
    g.place(5, 5, 5, "minecraft:stone", None)
    assert g.bounds() == ((5, 5, 5), (5, 5, 5))
    assert g.count_non_air() == 1


def test_air_carved_vs_unset_in_dense():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", None)
    g.place(1, 0, 0, AIR, None)  # carved air inside the bbox
    g.place(2, 0, 0, "minecraft:stone", None)
    arr, palette, _ = g.to_dense()
    assert arr.shape == (3, 1, 1)
    assert arr[0, 0, 0] == palette.index("minecraft:stone")
    assert arr[1, 0, 0] == palette.index(AIR)  # carved: palette index, not UNSET


def test_unset_cells_read_as_minus_one():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", None)
    g.place(2, 0, 0, "minecraft:stone", None)
    arr, _, _ = g.to_dense()
    assert arr[1, 0, 0] == UNSET == -1  # never placed


def test_empty_grid_to_dense():
    arr, palette, prov = VoxelGrid().to_dense()
    assert arr.shape == (0, 0, 0)
    assert arr.dtype == np.int32
    assert palette == []
    assert prov == {}


def test_negative_coordinates_allowed():
    g = VoxelGrid()
    g.place(-255, -255, -255, "minecraft:stone", None)
    assert g.bounds() == ((-255, -255, -255), (-255, -255, -255))


def test_bounds_error_names_axis_with_actual_vs_allowed():
    g = VoxelGrid(max_dims=(256, 256, 256))
    with pytest.raises(GridBoundsError, match="axis x"):
        g.place(300, 0, 0, "minecraft:stone", None)
    with pytest.raises(GridBoundsError) as ei:
        g.place(300, 0, 0, "minecraft:stone", None)
    assert "300" in str(ei.value) and "256" in str(ei.value)

    with pytest.raises(GridBoundsError, match="axis y"):
        g.place(0, -300, 0, "minecraft:stone", None)
    with pytest.raises(GridBoundsError, match="axis z"):
        g.place(0, 0, 256, "minecraft:stone", None)


def test_grid_bounds_error_is_mcbuilder_error():
    assert issubclass(GridBoundsError, McbuilderError)


def test_custom_max_dims():
    g = VoxelGrid(max_dims=(16, 32, 16))
    g.place(15, 31, 15, "minecraft:stone", None)
    with pytest.raises(GridBoundsError, match="axis x"):
        g.place(16, 0, 0, "minecraft:stone", None)
    assert g.max_dims == (16, 32, 16)


def test_non_int_coordinates_rejected():
    g = VoxelGrid()
    with pytest.raises(TypeError):
        g.place(1.5, 0, 0, "minecraft:stone", None)


def test_to_dense_drops_phantom_palette_entries():
    g = VoxelGrid()
    g.place(0, 0, 0, "minecraft:stone", ("a.py", 1))
    g.place(0, 0, 0, "minecraft:dirt", ("a.py", 2))  # stone fully overwritten
    arr, palette, prov = g.to_dense()
    assert palette == ["minecraft:dirt"]
    assert arr[0, 0, 0] == 0
    assert prov == {0: ("a.py", 2)}


def test_overwrite_count_tracks_real_block_replacements():
    g = VoxelGrid()
    assert g.overwrite_count == 0
    g.place(0, 0, 0, "minecraft:stone", None)
    g.place(0, 0, 0, "minecraft:stone", None)  # same block: not counted
    assert g.overwrite_count == 0
    g.place(0, 0, 0, "minecraft:dirt", None)  # real -> different real
    assert g.overwrite_count == 1
    g.place(1, 0, 0, "minecraft:stone", None)
    g.place(1, 0, 0, "minecraft:air", None)  # carving: not counted
    assert g.overwrite_count == 1
    g.place(2, 0, 0, "minecraft:air", None)
    g.place(2, 0, 0, "minecraft:stone", None)  # air -> real: not counted
    assert g.overwrite_count == 1
