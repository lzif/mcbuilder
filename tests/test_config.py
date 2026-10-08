"""Unit tests for mcbuilder.config — no network, no side effects."""

from pathlib import Path

import pytest

from mcbuilder.config import McbuildConfig


def test_defaults():
    cfg = McbuildConfig()
    assert cfg.mc_version == "1.21.4"
    assert cfg.max_dimensions == (256, 256, 256)
    assert cfg.allowlist == []
    assert cfg.assets_dir is None


def test_load_full_toml(tmp_path):
    toml = tmp_path / "mcbuild.toml"
    toml.write_text(
        'mc_version = "26.2"\n'
        "max_dimensions = [128, 64, 128]\n"
        'allowlist = ["lostqol:waystone", "mymod:gizmo"]\n'
        'assets_dir = "/tmp/custom-assets"\n'
    )
    cfg = McbuildConfig.load(toml)
    assert cfg.mc_version == "26.2"
    assert cfg.max_dimensions == (128, 64, 128)
    assert cfg.allowlist == ["lostqol:waystone", "mymod:gizmo"]
    assert cfg.assets_dir == Path("/tmp/custom-assets")


def test_load_partial_toml_uses_defaults(tmp_path):
    toml = tmp_path / "mcbuild.toml"
    toml.write_text('mc_version = "26.2"\n')
    cfg = McbuildConfig.load(toml)
    assert cfg.mc_version == "26.2"
    assert cfg.max_dimensions == (256, 256, 256)
    assert cfg.allowlist == []
    assert cfg.assets_dir is None


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        McbuildConfig.load(tmp_path / "mcbuild.toml")


def test_load_invalid_toml_raises(tmp_path):
    toml = tmp_path / "mcbuild.toml"
    toml.write_text("mc_version = [unclosed\n")
    with pytest.raises(ValueError, match="invalid TOML"):
        McbuildConfig.load(toml)


def test_load_bad_dimensions_raises(tmp_path):
    toml = tmp_path / "mcbuild.toml"
    toml.write_text("max_dimensions = [256, 256]\n")
    with pytest.raises(ValueError, match="3 positive integers"):
        McbuildConfig.load(toml)


def test_load_bad_allowlist_raises(tmp_path):
    toml = tmp_path / "mcbuild.toml"
    toml.write_text('allowlist = "not-a-list"\n')
    with pytest.raises(ValueError, match="allowlist must be a list"):
        McbuildConfig.load(toml)


def test_find_walks_up_to_config(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "a" / "mcbuild.toml").write_text('mc_version = "26.2"\n')
    cfg = McbuildConfig.find(tmp_path / "a" / "b" / "c")
    assert cfg is not None
    assert cfg.mc_version == "26.2"


def test_find_accepts_file_start(tmp_path):
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "mcbuild.toml").write_text('mc_version = "26.1"\n')
    script = tmp_path / "proj" / "waystone.py"
    script.write_text("# builder script\n")
    cfg = McbuildConfig.find(script)
    assert cfg is not None
    assert cfg.mc_version == "26.1"


def test_find_returns_none_when_absent(tmp_path):
    deep = tmp_path / "x" / "y"
    deep.mkdir(parents=True)
    assert McbuildConfig.find(deep) is None


def test_resolve_assets_dir_default():
    cfg = McbuildConfig(mc_version="26.2")
    assert cfg.resolve_assets_dir() == Path.home() / ".cache" / "mcbuilder" / "26.2"


def test_resolve_assets_dir_explicit(tmp_path):
    cfg = McbuildConfig(assets_dir=tmp_path / "mine")
    assert cfg.resolve_assets_dir() == tmp_path / "mine"
