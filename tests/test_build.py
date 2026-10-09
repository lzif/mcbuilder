"""Tests for mcbuilder.build: Build DSL, batch scope, shapes, provenance."""

import random
import sys

import numpy as np
import pytest

from mcbuilder.blocks import parse
from mcbuilder.build import Build, BuildError
from mcbuilder.errors import McbuilderError
from mcbuilder.voxels import GridBoundsError, VoxelGrid


def _helper_box(b):
    b.box((5, 5, 5), (5, 5, 5), "minecraft:gold_block"); return sys._getframe().f_lineno


# -- batch scope ---------------------------------------------------------


def test_placements_require_with_block():
    b = Build()
    with pytest.raises(BuildError, match=r"placements must be inside `with BUILD:`"):
        b.set(0, 0, 0, "minecraft:stone")
    with pytest.raises(BuildError):
        b.box((0, 0, 0), (1, 1, 1), "minecraft:stone")


def test_with_block_allows_placements_and_nests():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
        with b:  # nested batch scope
            b.set(1, 0, 0, "minecraft:dirt")
        b.set(2, 0, 0, "minecraft:gold_block")
    assert b.grid.count_non_air() == 3


def test_sequential_with_blocks_accumulate():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    with b:
        b.set(1, 0, 0, "minecraft:dirt")
    assert b.grid.count_non_air() == 2


def test_build_error_is_mcbuilder_error():
    assert issubclass(BuildError, McbuilderError)


# -- provenance -----------------------------------------------------------


def test_provenance_points_at_caller_file_and_line():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone"); expected = sys._getframe().f_lineno
    _, _, prov = b.grid.to_dense()
    filename, lineno = prov[0]
    assert filename.endswith("test_build.py")
    assert lineno == expected


def test_provenance_skips_internal_package_frames():
    # _helper_box lives outside the mcbuilder package; the provenance must
    # point at its b.box(...) line, not at build.py internals.
    b = Build()
    with b:
        expected = _helper_box(b)
    _, palette, prov = b.grid.to_dense()
    idx = palette.index("minecraft:gold_block")
    filename, lineno = prov[idx]
    assert filename.endswith("test_build.py")
    assert lineno == expected


def test_provenance_first_placement_wins():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone"); first = sys._getframe().f_lineno
        b.set(9, 9, 9, "minecraft:stone"); _ = sys._getframe().f_lineno
    _, _, prov = b.grid.to_dense()
    assert prov[0][1] == first


# -- massing helpers -------------------------------------------------------


def test_box_corners_any_order_inclusive():
    b = Build()
    with b:
        b.box((2, 2, 2), (0, 0, 0), "minecraft:stone")
    assert b.grid.count_non_air() == 27
    assert b.grid.bounds() == ((0, 0, 0), (2, 2, 2))


def test_box_places_block_verbatim_no_inference():
    b = Build()
    with b:
        b.box((0, 0, 0), (1, 0, 0), "minecraft:oak_log")
    _, palette, _ = b.grid.to_dense()
    assert palette == ["minecraft:oak_log"]  # no axis guessed


def test_walls_hollow_no_floor_or_ceiling():
    b = Build()
    with b:
        b.walls((0, 0, 0), (2, 2, 2), "minecraft:stone_bricks")
    assert b.grid.count_non_air() == 24  # 8 per layer x 3 layers
    arr, _, _ = b.grid.to_dense()
    assert arr[1, 1, 1] == -1  # hollow center
    # walls span the full height, including top and bottom rows
    assert arr[0, 0, 1] != -1 and arr[0, 2, 1] != -1


def test_floor_is_height_one_at_c1_y():
    b = Build()
    with b:
        b.floor((0, 5, 0), (2, 9, 2), "minecraft:oak_planks")
    assert b.grid.count_non_air() == 9
    assert b.grid.bounds() == ((0, 5, 0), (2, 5, 2))


def test_set_overwrites_last_write_wins():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
        b.set(0, 0, 0, "minecraft:dirt")
    arr, palette, _ = b.grid.to_dense()
    assert palette[arr[0, 0, 0]] == "minecraft:dirt"


def test_air_is_legal_carving():
    b = Build()
    with b:
        b.box((0, 0, 0), (2, 0, 2), "minecraft:stone")
        b.set(1, 0, 1, "minecraft:air")
    assert b.grid.count_non_air() == 8


# -- roof_gable ------------------------------------------------------------


def _facing(block: str) -> str:
    return parse(block)[1]["facing"]


def test_roof_gable_ridge_x():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (4, 0, 4), "minecraft:oak_stairs", "x")
    assert b.grid.bounds() == ((0, 0, 0), (4, 2, 4))
    arr, palette, _ = b.grid.to_dense()
    at = lambda x, y, z: palette[arr[x, y, z]]
    # north eave (z=0) ascends toward +z: low side faces north
    assert _facing(at(2, 0, 0)) == "north"
    assert _facing(at(2, 0, 4)) == "south"
    assert _facing(at(2, 1, 1)) == "north"
    assert _facing(at(2, 1, 3)) == "south"
    # ridge row (odd span) faces the min-side eave
    assert _facing(at(2, 2, 2)) == "north"
    # gap above the ridge-side slope is empty
    assert arr[2, 1, 2] == -1
    # half defaults to bottom
    assert parse(at(0, 0, 0))[1]["half"] == "bottom"


def test_roof_gable_ridge_z():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (4, 0, 4), "minecraft:oak_stairs", "z")
    arr, palette, _ = b.grid.to_dense()
    at = lambda x, y, z: palette[arr[x, y, z]]
    assert _facing(at(0, 0, 2)) == "west"
    assert _facing(at(4, 0, 2)) == "east"
    assert _facing(at(2, 2, 2)) == "west"  # ridge faces min-side eave


def test_roof_gable_even_span_has_no_ridge_row():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (3, 0, 3), "minecraft:oak_stairs", "x")
    # span 4 -> 2 pairs, top at y=1
    assert b.grid.bounds() == ((0, 0, 0), (3, 1, 3))
    assert b.grid.count_non_air() == 2 * 2 * 4


def test_roof_gable_ridge_required():
    b = Build()
    with b:
        with pytest.raises(BuildError, match="ridge"):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs", "y")
        with pytest.raises(TypeError):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs")  # type: ignore[call-arg]


def test_roof_gable_rejects_prefaced_facing():
    b = Build()
    with b:
        with pytest.raises(BuildError, match="facing"):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs[facing=north]", "x")


def test_roof_gable_preserves_other_props_and_nbt():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (2, 0, 0), "minecraft:oak_stairs[waterlogged=true]", "x")
    _, palette, _ = b.grid.to_dense()
    name, props, _ = parse(palette[0])
    assert name == "minecraft:oak_stairs"
    assert props["waterlogged"] == "true"
    assert props["facing"] == "north"


# -- recenter ---------------------------------------------------------------


def test_recenter_xz_to_origin_y_untouched():
    b = Build()
    with b:
        b.box((0, 3, 0), (8, 7, 8), "minecraft:stone")
    b.recenter()
    assert b.grid.bounds() == ((-4, 3, -4), (4, 7, 4))


def test_recenter_even_width_rounds_half_up():
    b = Build()
    with b:
        b.box((0, 0, 0), (9, 0, 9), "minecraft:stone")
    b.recenter()
    assert b.grid.bounds() == ((-5, 0, -5), (4, 0, 4))


def test_recenter_empty_is_noop():
    Build().recenter()  # must not raise


# -- determinism / rng --------------------------------------------------------


def _script(b: Build):
    with b:
        b.box((0, 0, 0), (4, 4, 4), "minecraft:stone")
        r = b.rng()
        for _ in range(10):
            b.set(r.randrange(0, 5), 5, r.randrange(0, 5), "minecraft:torch")


def test_same_seed_same_grid():
    b1, b2 = Build(seed=7), Build(seed=7)
    _script(b1)
    _script(b2)
    a1, p1, _ = b1.grid.to_dense()
    a2, p2, _ = b2.grid.to_dense()
    assert p1 == p2
    assert np.array_equal(a1, a2)


def test_rng_matches_seeded_random():
    b = Build(seed=7)
    assert b.rng() is b.rng()  # sole source: same instance
    ref = random.Random(7)
    assert [b.rng().random() for _ in range(3)] == [ref.random() for _ in range(3)]


# -- config / introspection ----------------------------------------------------


def test_views_config_stored_raw_without_views_module_hook():
    b = Build(seed=7, views=["top", "iso"])
    assert b.views_config == ["top", "iso"]
    assert b.seed == 7
    b.set_views(["az000_el025"])
    assert b.views_config == ["az000_el025"]
    b.set_views(None)
    assert b.views_config is None


def test_grid_property_exposes_voxel_grid():
    b = Build(max_dimensions=(16, 16, 16))
    assert isinstance(b.grid, VoxelGrid)
    with b:
        with pytest.raises(GridBoundsError):
            b.set(20, 0, 0, "minecraft:stone")


# -- review fixes (post-implement review round 1) ---------------------------


def test_roof_gable_canonicalizes_nbt_keys():
    """roof_gable must emit fully canonical palette keys (finding #1).

    NBT top-level keys sorted, like Build.set produces — otherwise the
    same blockstate lands in two palette entries and block_counts splits.
    """
    b = Build(seed=1)
    with b:
        b.roof_gable((0, 0, 0), (4, 0, 4), "minecraft:oak_stairs{z:1,a:2}", ridge="x")
    _, palette, _ = b.grid.to_dense()
    assert any("{a:2,z:1}" in p for p in palette)
    assert not any("{z:1,a:2}" in p for p in palette)


def test_set_views_bare_string_not_exploded():
    """A bare string is one view spec, not a char list (finding #5)."""
    b = Build(seed=1)
    b.set_views("az045_el025;top")
    assert b.views_config == ["az045_el025;top"]


def test_render_enforces_36_view_cap(tmp_path):
    """The harness path enforces the 36-view cap like the CLI (finding #2)."""
    from mcbuilder.views import View, ViewError

    b = Build(seed=1)
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    views = [View(azimuth=float(i % 360), elevation=25.0, label=f"v{i}") for i in range(40)]
    with pytest.raises(ViewError):
        b.render(tmp_path, views=views)


def test_build_validate_uses_registry():
    """Build.validate() runs registry validation over the palette (finding #4)."""
    from mcbuilder.registry import Registry

    reg = Registry({"minecraft:stone": {"properties": {}}}, version="test")
    b = Build(seed=1)
    with b:
        b.set(0, 0, 0, "minecraft:stone")
        b.set(1, 0, 0, "minecraft:nope_block")
    errors, _warnings = b.validate(reg)
    assert any("nope_block" in e["block"] for e in errors)
    assert not any("minecraft:stone" in e["block"] for e in errors)
