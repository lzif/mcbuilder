"""Schema tests for mcbuilder.report (PLAN section 4.6)."""

import json

from mcbuilder.report import build_report, view_entry, write_report
from mcbuilder.views import View


def _sample_views():
    v = View(azimuth=45.0, elevation=25.0, label="az045_el025")
    return [view_entry(file="az045_el025.png", view=v)]


def test_schema_keys():
    report = build_report(
        errors=[{"block": "minecraft:ston", "message": "unknown block",
                 "suggestions": ["minecraft:stone"], "at": "waystone.py:42"}],
        warnings=[{"code": "bbox_blowup", "message": ">80% air"}],
        block_counts={"minecraft:stone": 12},
        dimensions=(9, 8, 9),
        views=_sample_views(),
        run_dir="dist/run-003",
    )
    assert set(report.keys()) == {
        "errors", "warnings", "block_counts",
        "dimensions", "views", "run_dir",
    }
    assert report["dimensions"] == [9, 8, 9]
    assert report["run_dir"] == "dist/run-003"


def test_view_entry_shape():
    (entry,) = _sample_views()
    assert entry == {
        "file": "az045_el025.png",
        "azimuth": 45.0,
        "elevation": 25.0,
        "label": "az045_el025",
        "directions_untrusted": True,
    }


def test_error_at_may_be_null():
    report = build_report(
        errors=[{"block": "x", "message": "m", "suggestions": [], "at": None}],
        warnings=[], block_counts={}, dimensions=None, views=[],
        run_dir="dist/run-001",
    )
    assert report["errors"][0]["at"] is None
    assert report["dimensions"] is None


def test_inputs_are_copied():
    errors = [{"block": "x", "message": "m", "suggestions": [], "at": None}]
    report = build_report(errors=errors, warnings=[], block_counts={},
                          dimensions=None, views=[], run_dir="r")
    errors[0]["block"] = "mutated"
    assert report["errors"][0]["block"] == "x"


def test_write_report_json_round_trip(tmp_path):
    report = build_report(
        errors=[], warnings=[],
        block_counts={"minecraft:stone": 3},
        dimensions=(3, 3, 3),
        views=_sample_views(),
        run_dir="dist/run-001",
    )
    path = tmp_path / "nested" / "report.json"
    write_report(report, path)
    assert path.exists()
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert json.loads(raw) == report
    # indent=2 formatting
    assert '\n  "errors"' in raw
