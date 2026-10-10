"""Tests for mcbuilder.diff (diff between runs, GitHub issue #1 item 5).

These call the underlying diff functions directly — not the CLI — over
tiny hand-built run dirs: two BUILDs differing by a few cells, exported
to .nbt through the real serializer with a hand-written report.json.
A couple of thin CLI tests check clean errors and exit codes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from mcbuilder import build as build_mod
from mcbuilder import diff as diff_mod
from mcbuilder import export_nbt as export_nbt_mod
from mcbuilder import report as report_mod
from mcbuilder.cli import main


@pytest.fixture(autouse=True)
def _pin_hashseed(monkeypatch):
    # main() re-execs the process when PYTHONHASHSEED is unset; pin it here.
    monkeypatch.setenv("PYTHONHASHSEED", "0")


# ---------------------------------------------------------------------------
# fixtures: tiny hand-built run dirs (real BUILD + real .nbt serializer)
# ---------------------------------------------------------------------------

def _build_a(b) -> None:
    b.box((0, 0, 0), (1, 0, 1), "minecraft:stone")  # 4 stone cells
    b.set(0, 1, 0, "minecraft:oak_planks")


def _build_b(b) -> None:
    # (0,0,0) and (0,0,1) removed; planks -> stone; one cobble added
    b.box((1, 0, 0), (1, 0, 1), "minecraft:stone")
    b.set(0, 1, 0, "minecraft:stone")
    b.set(2, 0, 0, "minecraft:cobblestone")


def _build_a_shifted(b) -> None:
    # same shape as _build_a, translated wholesale
    b.box((10, 5, 3), (11, 5, 4), "minecraft:stone")
    b.set(10, 6, 3, "minecraft:oak_planks")


def _stairs_north(b) -> None:
    b.set(0, 0, 0, "minecraft:oak_stairs[facing=north,half=bottom]")


def _stairs_south(b) -> None:
    b.set(0, 0, 0, "minecraft:oak_stairs[facing=south,half=bottom]")


def _make_run(dist: Path, name: str, build_fn, *, views=()) -> Path:
    """Build a fake run dir: real BUILD -> real .nbt + hand-written report.json."""
    b = build_mod.Build(seed=1)
    with b:
        build_fn(b)
    run = dist / name
    run.mkdir(parents=True)
    export_nbt_mod.write_structure_nbt(
        b.grid, run / "hut.nbt", data_version=4189, include_air=False
    )
    views_entries = [
        {
            "file": f"previews/{label}.png",
            "label": label,
            "azimuth": 45,
            "elevation": 25,
            "directions_untrusted": True,
            "directions_trusted": False,
        }
        for label in views
    ]
    report = report_mod.build_report(
        errors=[],
        warnings=[],
        block_counts={},
        dimensions=None,
        views=views_entries,
        run_dir=str(run),
        artifacts=[{"file": "hut.nbt", "format": "nbt", "data_version": 4189}],
        overwritten_placements=0,
    )
    report_mod.write_report(report, run / "report.json")
    return run


# ---------------------------------------------------------------------------
# core diff
# ---------------------------------------------------------------------------

def test_diff_reports_exact_added_removed_changed(tmp_path):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a)
    b = _make_run(dist, "run-002", _build_b)
    d = diff_mod.diff_run_dirs(a, b)
    assert d.added == [((2, 0, 0), "minecraft:cobblestone")]
    assert d.removed == [
        ((0, 0, 0), "minecraft:stone"),
        ((0, 0, 1), "minecraft:stone"),
    ]
    assert d.changed == [
        ((0, 1, 0), "minecraft:oak_planks", "minecraft:stone"),
    ]
    assert d.cells_a == 5
    assert d.cells_b == 4
    assert not d.is_empty
    assert d.total == 4


def test_diff_identical_runs(tmp_path):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a)
    b = _make_run(dist, "run-002", _build_a)
    d = diff_mod.diff_run_dirs(a, b)
    assert d.is_empty
    assert d.added == d.removed == d.changed == []
    text = diff_mod.format_diff(d, "run-001", "run-002")
    assert "no differences" in text
    assert "5 cells" in text


def test_diff_anchors_at_bbox_origin(tmp_path):
    # A wholesale move reports as identical: positions are bbox-min offsets.
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a)
    b = _make_run(dist, "run-002", _build_a_shifted)
    assert diff_mod.diff_run_dirs(a, b).is_empty


def test_diff_detects_blockstate_change(tmp_path):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _stairs_north)
    b = _make_run(dist, "run-002", _stairs_south)
    d = diff_mod.diff_run_dirs(a, b)
    assert d.changed == [
        (
            (0, 0, 0),
            "minecraft:oak_stairs[facing=north,half=bottom]",
            "minecraft:oak_stairs[facing=south,half=bottom]",
        )
    ]


def test_diff_reversed_direction(tmp_path):
    # Diffing B -> A inverts added/removed and flips the changed pair.
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a)
    b = _make_run(dist, "run-002", _build_b)
    d = diff_mod.diff_run_dirs(b, a)
    assert d.added == [
        ((0, 0, 0), "minecraft:stone"),
        ((0, 0, 1), "minecraft:stone"),
    ]
    assert d.removed == [((2, 0, 0), "minecraft:cobblestone")]
    assert d.changed == [
        ((0, 1, 0), "minecraft:stone", "minecraft:oak_planks"),
    ]


def test_format_diff_reports_counts_and_caps_entries(tmp_path):
    dist = tmp_path / "dist"

    def ten_a(b):
        b.box((0, 0, 0), (9, 0, 0), "minecraft:stone")

    def ten_b(b):
        b.box((0, 0, 0), (9, 0, 0), "minecraft:cobblestone")

    a = _make_run(dist, "run-001", ten_a)
    b = _make_run(dist, "run-002", ten_b)
    d = diff_mod.diff_run_dirs(a, b)
    text = diff_mod.format_diff(d, "run-001", "run-002", max_entries=3)
    assert "10 changed cells: 0 added, 0 removed, 10 replaced" in text
    assert text.count("\n  ~ ") == 3
    assert "... 7 more changes not shown (use --max N)" in text


# ---------------------------------------------------------------------------
# run id resolution + error paths
# ---------------------------------------------------------------------------

def test_resolve_run_dir_accepts_bare_number(tmp_path):
    dist = tmp_path / "dist"
    (dist / "run-007").mkdir(parents=True)
    assert diff_mod.resolve_run_dir(dist, "007").name == "run-007"
    assert diff_mod.resolve_run_dir(dist, "run-007").name == "run-007"


def test_resolve_unknown_run_is_clean_error(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(diff_mod.DiffError, match="unknown run"):
        diff_mod.resolve_run_dir(dist, "run-009")


def test_resolve_rejects_path_traversal(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    with pytest.raises(diff_mod.DiffError, match="invalid run id"):
        diff_mod.resolve_run_dir(dist, "../secret")


def test_load_run_voxels_without_artifact_is_clean_error(tmp_path):
    # A run that failed validation exports no .nbt: diff must say so.
    dist = tmp_path / "dist"
    run = dist / "run-001"
    run.mkdir(parents=True)
    report = report_mod.build_report(
        errors=[{"message": "boom"}],
        warnings=[],
        block_counts={},
        dimensions=None,
        views=[],
        run_dir=str(run),
        artifacts=[],
        overwritten_placements=0,
    )
    report_mod.write_report(report, run / "report.json")
    with pytest.raises(diff_mod.DiffError, match="no .nbt artifact"):
        diff_mod.load_run_voxels(run)


def test_load_run_voxels_without_report_is_clean_error(tmp_path):
    run = tmp_path / "run-001"
    run.mkdir()
    with pytest.raises(diff_mod.DiffError, match="no report.json"):
        diff_mod.load_run_voxels(run)


# ---------------------------------------------------------------------------
# comparison image
# ---------------------------------------------------------------------------

def test_comparison_image_is_side_by_side(tmp_path):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a, views=["iso"])
    b = _make_run(dist, "run-002", _build_b, views=["iso"])
    for run in (a, b):
        (run / "previews").mkdir()
        Image.new("RGB", (120, 80), (90, 90, 200)).save(run / "previews" / "iso.png")
    d = diff_mod.diff_run_dirs(a, b)
    out = dist / "diff-run-001-run-002.png"
    made = diff_mod.comparison_image(a, b, d, out)
    assert made == out
    assert out.is_file()
    im = Image.open(out)
    assert im.width > 120  # two panels + divider, wider than one panel
    assert out.stat().st_size > 100


def test_comparison_image_none_without_shared_view(tmp_path):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a)  # no previews at all
    b = _make_run(dist, "run-002", _build_b)
    d = diff_mod.diff_run_dirs(a, b)
    assert diff_mod.comparison_image(a, b, d, dist / "x.png") is None
    assert not (dist / "x.png").exists()


# ---------------------------------------------------------------------------
# thin CLI tests: exit codes + clean errors
# ---------------------------------------------------------------------------

def test_cli_diff_reports_changes_and_exits_1(tmp_path, capsys):
    dist = tmp_path / "dist"
    _make_run(dist, "run-001", _build_a)
    _make_run(dist, "run-002", _build_b)
    assert main(["diff", "run-001", "run-002", "--out", str(dist)]) == 1
    out, err = capsys.readouterr()
    assert "diff run-001 -> run-002" in out
    assert "4 changed cells: 1 added, 2 removed, 1 replaced" in out
    assert "+ (2, 0, 0) minecraft:cobblestone" in out
    assert "- (0, 0, 0) minecraft:stone" in out
    assert "~ (0, 1, 0) minecraft:oak_planks -> minecraft:stone" in out
    assert "comparison: no shared preview view — image skipped" in out
    assert "Traceback" not in out + err


def test_cli_diff_identical_exits_0(tmp_path, capsys):
    dist = tmp_path / "dist"
    _make_run(dist, "run-001", _build_a)
    _make_run(dist, "run-002", _build_a)
    assert main(["diff", "run-001", "run-002", "--out", str(dist)]) == 0
    out, err = capsys.readouterr()
    assert "no differences" in out
    assert "Traceback" not in out + err


def test_cli_diff_unknown_run_is_clean_error(tmp_path, capsys):
    dist = tmp_path / "dist"
    dist.mkdir()
    assert main(["diff", "run-001", "run-002", "--out", str(dist)]) == 1
    out, err = capsys.readouterr()
    assert "unknown run" in err
    assert "Traceback" not in out + err


def test_cli_diff_writes_comparison_image(tmp_path, capsys):
    dist = tmp_path / "dist"
    a = _make_run(dist, "run-001", _build_a, views=["iso"])
    b = _make_run(dist, "run-002", _build_b, views=["iso"])
    for run in (a, b):
        (run / "previews").mkdir()
        Image.new("RGB", (120, 80), (90, 90, 200)).save(run / "previews" / "iso.png")
    assert main(["diff", "001", "002", "--out", str(dist)]) == 1
    out, _ = capsys.readouterr()
    img = dist / "diff-run-001-run-002.png"
    assert img.is_file()
    assert f"comparison: {img}" in out
