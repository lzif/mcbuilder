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
    line = sys._getframe().f_lineno + 1
    b.box((5, 5, 5), (5, 5, 5), "minecraft:gold_block")
    return line


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
        expected = sys._getframe().f_lineno + 1
        b.set(0, 0, 0, "minecraft:stone")
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
        first = sys._getframe().f_lineno + 1
        b.set(0, 0, 0, "minecraft:stone")
        b.set(9, 9, 9, "minecraft:stone")
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
        b.roof_gable((0, 0, 0), (4, 0, 4), "minecraft:oak_stairs", ridge="x")
    assert b.grid.bounds() == ((0, 0, 0), (4, 2, 4))
    arr, palette, _ = b.grid.to_dense()
    at = lambda x, y, z: palette[arr[x, y, z]]
    # north eave (z=0) ascends toward +z: tall backs face uphill (south)
    assert _facing(at(2, 0, 0)) == "south"
    assert _facing(at(2, 0, 4)) == "north"
    assert _facing(at(2, 1, 1)) == "south"
    assert _facing(at(2, 1, 3)) == "north"
    # ridge row (odd span) faces the min-side eave, continuing the
    # max-side (south) slope
    assert _facing(at(2, 2, 2)) == "north"
    # gap above the ridge-side slope is empty
    assert arr[2, 1, 2] == -1
    # half defaults to bottom
    assert parse(at(0, 0, 0))[1]["half"] == "bottom"


def test_roof_gable_ridge_z():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (4, 0, 4), "minecraft:oak_stairs", ridge="z")
    arr, palette, _ = b.grid.to_dense()
    at = lambda x, y, z: palette[arr[x, y, z]]
    assert _facing(at(0, 0, 2)) == "east"  # west eave ascends eastward
    assert _facing(at(4, 0, 2)) == "west"  # east eave ascends westward
    assert _facing(at(2, 2, 2)) == "west"  # ridge faces min-side eave


def test_roof_gable_even_span_has_no_ridge_row():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (3, 0, 3), "minecraft:oak_stairs", ridge="x")
    # span 4 -> 2 pairs, top at y=1
    assert b.grid.bounds() == ((0, 0, 0), (3, 1, 3))
    assert b.grid.count_non_air() == 2 * 2 * 4


def test_roof_gable_ridge_required():
    b = Build()
    with b:
        with pytest.raises(McbuilderError, match="ridge"):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs", ridge="y")
        with pytest.raises(TypeError):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs")  # type: ignore[call-arg]


def test_roof_gable_rejects_prefaced_facing():
    b = Build()
    with b:
        with pytest.raises(McbuilderError, match="facing"):
            b.roof_gable((0, 0, 0), (2, 0, 2), "minecraft:oak_stairs[facing=north]", ridge="x")


def test_roof_gable_preserves_other_props_and_nbt():
    b = Build()
    with b:
        b.roof_gable((0, 0, 0), (2, 0, 0), "minecraft:oak_stairs[waterlogged=true]", ridge="x")
    _, palette, _ = b.grid.to_dense()
    name, props, _ = parse(palette[0])
    assert name == "minecraft:oak_stairs"
    assert props["waterlogged"] == "true"
    assert props["facing"] == "north"


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
    from mcbuilder.render.views import View, ViewError

    b = Build(seed=1)
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    views = [View(azimuth=float(i % 360), elevation=25.0, label=f"v{i}") for i in range(40)]
    with pytest.raises(ViewError):
        b.render(tmp_path, views=views)


def test_render_discovers_assets_when_dir_not_given(tmp_path):
    """assets_dir=None must do CLI-like cache discovery, not silently
    render every block magenta (the agent footgun)."""
    from pathlib import Path

    cache = Path.home() / ".cache" / "mcbuilder" / "26.2"
    if not (cache / "client" / "assets" / "minecraft").is_dir():
        pytest.skip("no local 26.2 asset cache")
    from PIL import Image

    b = Build(seed=1)
    with b:
        b.set(0, 0, 0, "minecraft:grass_block")
    paths = b.render(tmp_path, views=["top"], tier="faithful")
    assert len(paths) == 1
    img = Image.open(paths[0]).convert("RGB")
    # Grass green present, magenta fallback absent.
    px = np.asarray(img).reshape(-1, 3)
    assert any(g > 100 > r for r, g, _b in px), "no green texels rendered"
    assert not any(r > 180 and g < 100 and b > 180 for r, g, b in px), (
        "magenta fallback rendered despite cached assets"
    )


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


# -- one-shot helpers return the placed Geometry ---------------------------


def test_get_returns_block_string():
    b = Build()
    with b:
        b.set(3, 4, 5, "minecraft:stone")
    assert b.get(3, 4, 5) == "minecraft:stone"  # read-only: outside `with`


def test_get_returns_none_for_unplaced_cell():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    assert b.get(9, 9, 9) is None
    assert b.get(1, 0, 0) is None


def test_get_returns_none_for_explicit_air():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
        b.set(0, 0, 0, "minecraft:air")  # carve by air: get still reads None
    assert b.get(0, 0, 0) is None


def test_get_returns_canonical_form_with_props():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:oak_stairs[half=top,facing=south]")
    assert b.get(0, 0, 0) == "minecraft:oak_stairs[facing=south,half=top]"


def test_count_returns_exact_int():
    b = Build()
    with b:
        b.box((0, 0, 0), (2, 2, 2), "minecraft:stone")
        b.set(0, 0, 0, "minecraft:dirt")  # overwrite one cell
    assert b.count("minecraft:stone") == 26
    assert b.count("minecraft:dirt") == 1
    assert b.count("minecraft:gold_block") == 0


def test_count_canonicalizes_query_block():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:oak_stairs[facing=north,half=top]")
    # property order in the query never matters ...
    assert b.count("minecraft:oak_stairs[half=top,facing=north]") == 1
    # ... but the property *set* must match verbatim
    assert b.count("minecraft:oak_stairs[facing=north]") == 0


def test_count_air_counts_carved_cells():
    b = Build()
    with b:
        b.box((0, 0, 0), (2, 0, 2), "minecraft:stone")
        b.set(1, 0, 1, "minecraft:air")
    assert b.count("minecraft:air") == 1
    assert b.count("minecraft:stone") == 8


def test_find_returns_sorted_coord_list():
    b = Build()
    with b:
        b.set(5, 0, 0, "minecraft:gold_block")
        b.set(0, 9, 0, "minecraft:gold_block")
        b.set(0, 0, 3, "minecraft:gold_block")
        b.set(1, 1, 1, "minecraft:stone")
    assert b.find("minecraft:gold_block") == [(0, 0, 3), (0, 9, 0), (5, 0, 0)]
    assert b.find("minecraft:stone") == [(1, 1, 1)]
    assert b.find("minecraft:dirt") == []


def test_find_uses_canonical_exact_match():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:oak_stairs[facing=north]")
        b.set(1, 0, 0, "minecraft:oak_stairs[facing=north,half=top]")
    assert b.find("minecraft:oak_stairs[facing=north]") == [(0, 0, 0)]
    assert b.find("minecraft:oak_stairs[half=top,facing=north]") == [(1, 0, 0)]


def test_count_find_reject_malformed_block():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
    with pytest.raises(ValueError):
        b.count("not a block[[[")
    with pytest.raises(ValueError):
        b.find("not a block[[[")


def test_to_dense_axis_convention_axis0_is_x_axis2_is_z():
    """Pin the axis trap: array[i,j,k] == cell (minx+i, miny+j, minz+k).

    A non-cubic bbox makes a transposed mapping fail loudly: a run of
    3 along X must give shape (3, 1, 1), not (1, 1, 3).
    """
    b = Build()
    with b:
        b.box((0, 0, 0), (2, 0, 0), "minecraft:stone")  # 3 long in X
    arr, _, _ = b.grid.to_dense()
    assert arr.shape == (3, 1, 1)

    b = Build()
    with b:
        b.box((5, 7, 9), (5, 7, 11), "minecraft:stone")  # 3 long in Z, offset min
    arr, palette, _ = b.grid.to_dense()
    assert arr.shape == (1, 1, 3)
    # minx=5, miny=7, minz=9: arr[0,0,2] == cell (5, 7, 11)
    assert palette[arr[0, 0, 2]] == "minecraft:stone"
    # and the Y axis: a vertical run
    b = Build()
    with b:
        b.box((0, 0, 0), (0, 4, 0), "minecraft:stone")
    arr, _, _ = b.grid.to_dense()
    assert arr.shape == (1, 5, 1)


# -- carve: the subtractive primitive -----------------------------------------


def test_carve_removes_exactly_the_box_region():
    b = Build()
    with b:
        b.box((0, 0, 0), (4, 4, 4), "minecraft:stone")  # 125 cells
        b.carve((1, 1, 1), (3, 3, 3))  # hollow out the center
    assert b.count("minecraft:stone") == 125 - 27
    # carved interior reads as unset ...
    assert b.get(2, 2, 2) is None
    assert b.find("minecraft:stone") == sorted(
        (x, y, z)
        for x in range(5)
        for y in range(5)
        for z in range(5)
        if not (1 <= x <= 3 and 1 <= y <= 3 and 1 <= z <= 3)
    )
    # ... and everything outside the carved box is untouched
    assert b.get(0, 0, 0) == "minecraft:stone"
    assert b.get(4, 4, 4) == "minecraft:stone"
    arr, _, _ = b.grid.to_dense()
    assert arr[2, 2, 2] == -1  # UNSET: carved cells are deleted, not air


def test_carve_corners_any_order_inclusive():
    b = Build()
    with b:
        b.box((0, 0, 0), (2, 2, 2), "minecraft:stone")
        b.carve((2, 2, 2), (0, 0, 0))  # reversed corners: same box
    assert b.count("minecraft:stone") == 0
    assert b.grid.to_dense()[0].shape == (0, 0, 0)


def test_carve_empty_region_is_noop():
    b = Build()
    with b:
        b.set(0, 0, 0, "minecraft:stone")
        b.carve((10, 10, 10), (12, 12, 12))  # nothing there: must not raise
    assert b.count("minecraft:stone") == 1
    assert b.get(0, 0, 0) == "minecraft:stone"


def test_carve_removes_outright_not_air():
    """carve deletes cells (UNSET); set-to-air keeps a carved air cell."""
    b = Build()
    with b:
        b.box((0, 0, 0), (3, 0, 0), "minecraft:stone")  # 4 cells
        b.carve((1, 0, 0), (1, 0, 0))  # delete the second cell outright
        b.set(2, 0, 0, "minecraft:air")  # carve the third cell with air
    arr, palette, _ = b.grid.to_dense()
    from mcbuilder.voxels import AIR, UNSET

    # non-air bbox is ((0,0,0),(3,0,0)); both carved cells sit inside it
    assert palette[arr[0, 0, 0]] == "minecraft:stone"
    assert arr[1, 0, 0] == UNSET  # carved: deleted, reads as unset
    assert palette[arr[2, 0, 0]] == AIR  # carved air: palette index, not UNSET
    assert palette[arr[3, 0, 0]] == "minecraft:stone"
    assert b.get(1, 0, 0) is None
    assert b.get(2, 0, 0) is None  # get can't tell them apart — by design
    assert b.count("minecraft:air") == 1
    assert b.count("minecraft:stone") == 2


def test_carve_requires_batch_scope():
    b = Build()
    with pytest.raises(BuildError, match=r"placements must be inside `with BUILD:`"):
        b.carve((0, 0, 0), (1, 1, 1))


def test_carve_validates_corners_like_box():
    b = Build()
    with b:
        with pytest.raises(BuildError, match="3 ints"):
            b.carve((0, 0), (1, 1, 1))
        with pytest.raises(BuildError, match="must be ints"):
            b.carve((0, 0, 0.5), (1, 1, 1))


def test_carve_single_cell():
    b = Build()
    with b:
        b.box((0, 0, 0), (1, 0, 1), "minecraft:stone")
        b.carve((0, 0, 0), (0, 0, 0))
    assert b.count("minecraft:stone") == 3
    assert b.get(0, 0, 0) is None
    assert b.get(1, 0, 1) == "minecraft:stone"


# ------------------------------------------------- materials


def test_box_weighted_palette_is_deterministic_per_cell():
    import mcbuilder as mb

    spec = ["minecraft:stone", ("minecraft:mossy_cobblestone", 0.3)]
    b1, b2 = mb.Build(seed=42), mb.Build(seed=42)
    with b1:
        b1.box((0, 0, 0), (4, 0, 4), spec)
    with b2:
        b2.box((0, 0, 0), (4, 0, 4), spec)
    for x in range(5):
        for z in range(5):
            assert b1.get(x, 0, z) == b2.get(x, 0, z)
    # ~30% secondary: some of each must appear on a 5x5 patch
    got = {b1.get(x, 0, z) for x in range(5) for z in range(5)}
    assert got == {"minecraft:stone", "minecraft:mossy_cobblestone"}, got


def test_box_callable_material():
    import mcbuilder as mb

    b = mb.Build(seed=1)
    with b:
        b.box(
            (0, 0, 0),
            (2, 0, 0),
            lambda x, y, z: "minecraft:stone" if x % 2 == 0 else "minecraft:cobblestone",
        )
    assert b.get(0, 0, 0) == "minecraft:stone"
    assert b.get(1, 0, 0) == "minecraft:cobblestone"
    assert b.get(2, 0, 0) == "minecraft:stone"


def test_box_plain_string_unchanged():
    import mcbuilder as mb

    b = mb.Build(seed=1)
    with b:
        b.box((0, 0, 0), (1, 1, 1), "minecraft:stone")
    assert b.count("minecraft:stone") == 8


def test_resolve_material_rejects_bad_specs():
    from mcbuilder.errors import McbuilderError
    from mcbuilder.materials import resolve_material

    with pytest.raises(McbuilderError, match="empty"):
        resolve_material([], 0, 0, 0, seed=1)
    with pytest.raises(McbuilderError, match="negative"):
        resolve_material([("minecraft:stone", -1.0)], 0, 0, 0, seed=1)
    with pytest.raises(McbuilderError, match="sum to zero"):
        resolve_material([("minecraft:stone", 0.0)], 0, 0, 0, seed=1)
    with pytest.raises(McbuilderError, match="invalid palette entry"):
        resolve_material([123], 0, 0, 0, seed=1)
    with pytest.raises(McbuilderError, match="invalid material spec"):
        resolve_material(123, 0, 0, 0, seed=1)


# ------------------------------------------------- primitives


def test_build_primitives_place_and_return_absolute():
    import mcbuilder as mb

    b = mb.Build(seed=9)
    with b:
        g = b.cylinder((10, 0, 10), 2, 2, "minecraft:stone")
    assert g.bounds() == ((8, 0, 8), (12, 1, 12)), g.bounds()
    assert b.get(10, 0, 10) == "minecraft:stone"
    with b:
        b.sphere((0, 20, 0), 1, "minecraft:glass")
    assert b.get(0, 20, 0) == "minecraft:glass"
    assert b.get(0, 22, 0) is None
    with b:
        b.line((0, 30, 0), (3, 30, 0), "minecraft:oak_planks")
    assert b.get(3, 30, 0) == "minecraft:oak_planks"


def test_build_cylinder_rejects_bad_radius():
    import mcbuilder as mb
    from mcbuilder.errors import McbuilderError

    b = mb.Build(seed=1)
    with b:
        with pytest.raises(McbuilderError, match="radius"):
            b.cylinder((0, 0, 0), 0, 3, "minecraft:stone")
