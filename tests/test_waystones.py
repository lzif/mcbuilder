"""Integration tests for the waystone variant example scripts (v0.2).

The four 7x7x7 variants (examples/waystones/) are the first UGC content
pack for the LostQoL pipeline. These tests pin the structural contract
every variant must satisfy, using the REAL script loader and exporter:

- the script defines BUILD and builds without error;
- dimensions are exactly 7x7x7;
- ``lostqol:waystone`` sits at the pedestal top (3, 3, 3);
- the .nbt export round-trips with the waystone entry intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import mcbuilder.cli as cli
import mcbuilder.export_nbt as export_nbt_mod

WAYSTONES = Path(__file__).resolve().parent.parent / "examples" / "waystones"

VARIANTS = [
    "waystone_classic_ruin.py",
    "waystone_dark_ritual.py",
    "waystone_rustic_path.py",
    "waystone_skystead.py",
]


def _load(name):
    path = WAYSTONES / name
    if not path.exists():
        pytest.skip(f"waystone script not authored yet: {name}")
    module, build = cli._load_script(path)
    with build:
        pass  # scripts place inside their own `with BUILD:`; nothing to do
    return build


def _waystone_cell(build):
    arr, palette, _ = build.grid.to_dense()
    try:
        idx = palette.index("lostqol:waystone")
    except ValueError:
        return None
    cells = (arr == idx)
    coords = list(zip(*cells.nonzero()))
    assert len(coords) == 1, "exactly one waystone block per variant"
    x, y, z = coords[0]
    # to_dense crops to the bbox; recover world coords via bounds().
    (minx, miny, minz), _ = build.grid.bounds()
    return (int(x) + minx, int(y) + miny, int(z) + minz)


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_is_7x7x7(variant):
    build = _load(variant)
    arr, _, _ = build.grid.to_dense()
    assert list(arr.shape) == [7, 7, 7], f"{variant}: {arr.shape}"


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_waystone_at_pedestal_top(variant):
    build = _load(variant)
    assert _waystone_cell(build) == (3, 3, 3), variant


@pytest.mark.parametrize("variant", VARIANTS)
def test_variant_nbt_roundtrip(tmp_path, variant):
    build = _load(variant)
    out = tmp_path / f"{Path(variant).stem}.nbt"
    warnings = export_nbt_mod.write_structure_nbt(
        build.grid, out, data_version=4903, include_air=False
    )
    assert warnings == []
    import nbtlib

    f = nbtlib.load(str(out), gzipped=True)
    assert int(f["DataVersion"]) == 4903
    assert [int(v) for v in f["size"]] == [7, 7, 7]
    names = [str(e["Name"]) for e in f["palette"]]
    assert "lostqol:waystone" in names
    # The waystone entry carries no properties (plain custom block).
    entry = next(e for e in f["palette"] if str(e["Name"]) == "lostqol:waystone")
    assert "Properties" not in entry
