"""Tests for mcbuilder.cli.

These tests run against the REAL sibling components (build, voxels, views,
config, report, preview) — only the two network/filesystem-heavy seams are
patched:

- ``Registry.load`` -> a real ``Registry`` built from hand-made block data
  (the real loader reads ``<cache>/<version>/minecraft-data.json`` as written
  by ``assets fetch``).
- ``assets.fetch`` -> a local fake (the real one downloads from the network).

No stub files are written into src/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import mcbuilder.cli as cli
from mcbuilder.assets import AssetError
from mcbuilder.cli import main
from mcbuilder.registry import Registry


HANDMADE_BLOCKS = {
    "minecraft:stone": {"properties": {}},
    "minecraft:oak_planks": {"properties": {}},
    "minecraft:air": {"properties": {}},
}


@pytest.fixture(autouse=True)
def _pin_hashseed(monkeypatch):
    # main() re-execs the process when PYTHONHASHSEED is unset; pin it here.
    monkeypatch.setenv("PYTHONHASHSEED", "0")


@pytest.fixture(autouse=True)
def _registry(monkeypatch):
    reg = Registry(HANDMADE_BLOCKS, "test")
    monkeypatch.setattr(
        Registry, "load", classmethod(lambda cls, version, cache_dir: reg)
    )
    return reg


@pytest.fixture(autouse=True)
def _assets_fetch(monkeypatch):
    def fake_fetch(version, cache_dir):
        p = Path(cache_dir) / version
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr("mcbuilder.assets.fetch", fake_fetch)


# ---------------------------------------------------------------------------
# fixtures: tiny inline builder scripts (real DSL API)
# ---------------------------------------------------------------------------

VALID_SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["az045_el025", "top"])
with BUILD:
    BUILD.box((0, 0, 0), (2, 1, 2), "minecraft:stone")
    BUILD.set(1, 2, 1, "minecraft:oak_planks")
"""

UNKNOWN_BLOCK_SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=7)
with BUILD:
    BUILD.box((0, 0, 0), (1, 0, 1), "minecraft:stone")
    BUILD.set(0, 1, 0, "minecraft:ston")
"""

NO_BUILD_SCRIPT = """\
VALUE = 42
"""

RANDOM_SCRIPT = """\
import random
import mcbuilder as mb

BUILD = mb.Build(seed=1)
with BUILD:
    BUILD.set(0, 0, 0, "minecraft:stone")
"""

ALLOWLIST_SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=3)
with BUILD:
    BUILD.set(0, 0, 0, "custom:waystone")
"""

OUTSIDE_SCOPE_SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=1)
BUILD.set(0, 0, 0, "minecraft:stone")  # outside `with BUILD:` -> BuildError
"""

BROKEN_SCRIPT = """\
import mcbuilder as mb

BUILD = mb.Build(seed=1)
with BUILD:
    BUILD.set(0, 0, 0, undefined_name)
"""

CONFIG_TOML = """\
mc_version = "1.21.4"
allowlist = ["custom:waystone"]
"""


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _with_config(tmp_path: Path) -> Path:
    return _write(tmp_path, "mcbuild.toml", CONFIG_TOML)


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

def test_check_valid_script_passes(tmp_path, capsys):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 0
    out, err = capsys.readouterr()
    assert "OK" in out
    assert "0 errors" in out
    assert "19 blocks" in out  # 3*2*3 stone + 1 planks
    assert "Traceback" not in out + err


def test_check_unknown_block_fails_with_provenance(tmp_path, capsys):
    script = _write(tmp_path, "bad.py", UNKNOWN_BLOCK_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 1
    out, err = capsys.readouterr()
    assert "minecraft:ston" in out
    assert "did you mean" in out  # real registry suggestions
    # provenance join: error carries file:line of the bad placement
    assert f"bad.py:" in out
    assert "Traceback" not in out + err


def test_check_missing_build_is_clean_error(tmp_path, capsys):
    script = _write(tmp_path, "nobuild.py", NO_BUILD_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 1
    out, err = capsys.readouterr()
    assert "BUILD" in err
    assert "Traceback" not in out + err


def test_check_missing_script_file_is_clean_error(tmp_path, capsys):
    _with_config(tmp_path)
    assert main(["check", str(tmp_path / "nope.py")]) == 1
    out, err = capsys.readouterr()
    assert "not found" in err
    assert "Traceback" not in out + err


def test_check_script_import_error_is_clean(tmp_path, capsys):
    script = _write(tmp_path, "broken.py", BROKEN_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 1
    out, err = capsys.readouterr()
    assert "failed to import" in err
    assert "NameError" in err
    assert "Traceback" not in out + err


def test_check_placement_outside_scope_is_clean_error(tmp_path, capsys):
    script = _write(tmp_path, "scope.py", OUTSIDE_SCOPE_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 1
    out, err = capsys.readouterr()
    assert "with BUILD" in err
    assert "Traceback" not in out + err


def test_check_warns_on_random_import(tmp_path, capsys):
    script = _write(tmp_path, "rnd.py", RANDOM_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 0  # warn, don't error
    out, _ = capsys.readouterr()
    assert "warning" in out
    assert "rng()" in out


def test_check_allowlisted_block_passes_with_warning(tmp_path, capsys):
    script = _write(tmp_path, "custom.py", ALLOWLIST_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 0
    out, _ = capsys.readouterr()
    assert "warning" in out
    assert "unvalidated" in out


def test_check_creates_no_run_dir(tmp_path):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    assert main(["check", str(script)]) == 0
    assert not (tmp_path / "dist").exists()


def test_check_without_config_uses_defaults(tmp_path, capsys):
    # No mcbuild.toml anywhere: default config (mc_version 1.21.4) applies.
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    assert main(["check", str(script)]) == 0
    out, err = capsys.readouterr()
    assert "OK" in out
    assert "Traceback" not in out + err


def test_check_explicit_config_missing_is_clean_error(tmp_path, capsys):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    assert main(["check", str(script), "--config", str(tmp_path / "no.toml")]) == 1
    out, err = capsys.readouterr()
    assert "config not found" in err
    assert "Traceback" not in out + err


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def test_run_creates_run001_with_report(tmp_path, capsys):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["run", str(script), "--out", str(out_dir)]) == 0

    run = out_dir / "run-001"
    assert run.is_dir()
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert report["errors"] == []
    # survival material/shopping list: post-crop, air excluded
    assert report["block_counts"] == {
        "minecraft:stone": 18,
        "minecraft:oak_planks": 1,
    }
    assert report["dimensions"] == [3, 3, 3]
    assert report["views"] == []
    assert report["run_dir"] == str(run)
    # the .nbt deploy artifact is written and recorded in report.json
    assert (run / "hut.nbt").is_file()
    assert report["artifacts"] == [
        {"file": "hut.nbt", "format": "nbt", "data_version": 4189}
    ]
    assert not any("deploy format pending" in str(w) for w in report["warnings"])

    out, err = capsys.readouterr()
    assert "run-001" in out
    assert "Traceback" not in out + err


def test_run_second_run_creates_run002(tmp_path):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["run", str(script), "--out", str(out_dir)]) == 0
    assert main(["run", str(script), "--out", str(out_dir)]) == 0
    assert (out_dir / "run-001" / "report.json").is_file()
    assert (out_dir / "run-002" / "report.json").is_file()


def test_run_with_preview_uses_script_views(tmp_path):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["run", str(script), "--out", str(out_dir), "--preview"]) == 0

    run = out_dir / "run-001"
    previews = sorted((run / "previews").glob("*.png"))
    assert [p.name for p in previews] == ["az045_el025.png", "top.png"]
    # real PNGs, not placeholders
    assert all(p.stat().st_size > 100 for p in previews)

    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert len(report["views"]) == 2
    v0, v1 = report["views"]
    assert v0["file"] == "previews/az045_el025.png"
    assert (v0["azimuth"], v0["elevation"], v0["label"]) == (45, 25, "az045_el025")
    assert v1["file"] == "previews/top.png"
    assert (v1["azimuth"], v1["elevation"], v1["label"]) == (0, 90, "top")
    for v in report["views"]:
        assert v["directions_untrusted"] is True  # fast tier


def test_run_views_flag_overrides_script_config(tmp_path):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert (
        main(["run", str(script), "--out", str(out_dir), "--preview", "--views", "iso"])
        == 0
    )
    previews = list((out_dir / "run-001" / "previews").glob("*.png"))
    assert [p.name for p in previews] == ["iso.png"]


def test_run_count_appends_orbit(tmp_path):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert (
        main(["run", str(script), "--out", str(out_dir), "--preview", "--count", "4"])
        == 0
    )
    # 2 script views + 4-orbit appended
    previews = list((out_dir / "run-001" / "previews").glob("*.png"))
    assert len(previews) == 6


def test_run_errors_skip_preview_and_artifact(tmp_path, capsys):
    script = _write(tmp_path, "bad.py", UNKNOWN_BLOCK_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["run", str(script), "--out", str(out_dir), "--preview"]) == 1

    run = out_dir / "run-001"
    report = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert len(report["errors"]) == 1
    assert "minecraft:ston" in report["errors"][0]["message"]
    assert "bad.py:" in report["errors"][0]["at"]
    assert not (run / "previews").exists()

    out, err = capsys.readouterr()
    assert "Traceback" not in out + err


def test_run_invalid_views_is_clean_error(tmp_path, capsys):
    script = _write(tmp_path, "hut.py", VALID_SCRIPT)
    _with_config(tmp_path)
    out_dir = tmp_path / "dist"
    assert main(["run", str(script), "--out", str(out_dir), "--views", "bogus"]) == 1
    out, err = capsys.readouterr()
    assert "invalid views" in err
    assert "Traceback" not in out + err
    assert not (out_dir / "run-001").exists()


def test_export_artifact_writes_nbt(tmp_path):
    # _export_artifact writes the vanilla structure .nbt and reports the
    # DataVersion it resolved (table fallback: no version.json in cache).
    import nbtlib

    from mcbuilder import build as build_mod
    from mcbuilder import config as config_mod

    b = build_mod.Build(seed=7)
    with b:
        b.box((0, 0, 0), (1, 0, 1), "minecraft:stone")
    cfg = config_mod.McbuildConfig(mc_version="1.21.4")
    path, data_version, warnings = cli._export_artifact(
        b.grid, tmp_path, "hut", cfg=cfg, include_air=False
    )
    assert path == tmp_path / "hut.nbt"
    assert data_version == 4189
    assert warnings == []
    f = nbtlib.load(str(path), gzipped=True)
    assert int(f["DataVersion"]) == 4189
    assert [int(v) for v in f["size"]] == [2, 1, 2]
    assert len(list(f["blocks"])) == 4


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------

def test_assets_fetch(tmp_path, capsys):
    cache = tmp_path / "cache"
    assert main(["assets", "fetch", "--version", "1.21.4", "--cache-dir", str(cache)]) == 0
    out, _ = capsys.readouterr()
    assert "1.21.4" in out
    assert (cache / "1.21.4").is_dir()


def test_assets_fetch_failure_is_clean_error(tmp_path, capsys, monkeypatch):
    def boom(version, cache_dir):
        raise AssetError("network down")

    monkeypatch.setattr("mcbuilder.assets.fetch", boom)
    assert main(["assets", "fetch", "--version", "1.21.4"]) == 1
    out, err = capsys.readouterr()
    assert "assets fetch failed" in err
    assert "Traceback" not in out + err
