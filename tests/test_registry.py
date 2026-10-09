"""Unit tests for mcbuilder.registry — all offline, tiny fake registry."""

import json
import sys
import types

import pytest

from mcbuilder.errors import RegistryError
from mcbuilder.registry import Registry, normalize_block_data

FAKE_BLOCKS = {
    "minecraft:stone": {"properties": {}},
    "minecraft:oak_stairs": {
        "properties": {
            "facing": ["north", "south", "west", "east"],
            "half": ["top", "bottom"],
            "waterlogged": ["true", "false"],
        }
    },
    "minecraft:oak_log": {"properties": {"axis": ["x", "y", "z"]}},
    "minecraft:chest": {"properties": {"facing": ["north", "south", "west", "east"]}},
}


@pytest.fixture()
def registry():
    return Registry(FAKE_BLOCKS, "test-1.0")


def test_all_legal_palette(registry):
    errors, warnings = registry.validate(
        ["minecraft:stone", "minecraft:oak_stairs[facing=north,half=bottom]"]
    )
    assert errors == []
    assert warnings == []


def test_unknown_name_has_suggestions(registry):
    errors, warnings = registry.validate(["minecraft:oak_stair"])
    assert len(errors) == 1
    err = errors[0]
    assert err["block"] == "minecraft:oak_stair"
    assert "unknown block" in err["message"]
    assert "minecraft:oak_stairs" in err["suggestions"]
    assert warnings == []


def test_illegal_property_value_lists_legal_values(registry):
    errors, _ = registry.validate(["minecraft:oak_stairs[facing=up]"])
    assert len(errors) == 1
    assert "illegal value 'up'" in errors[0]["message"]
    assert "north" in errors[0]["message"]  # legal values listed
    assert errors[0]["suggestions"] == []


def test_unknown_property_name(registry):
    errors, _ = registry.validate(["minecraft:oak_stairs[colour=red]"])
    assert len(errors) == 1
    assert "unknown property 'colour'" in errors[0]["message"]
    assert "facing" in errors[0]["message"]


def test_allowlisted_custom_block_passes_with_warning(registry):
    errors, warnings = registry.validate(
        ["lostqol:waystone{Owner:'Luki'}"], allowlist=["lostqol:waystone"]
    )
    assert errors == []
    assert len(warnings) == 1
    assert warnings[0]["block"] == "lostqol:waystone{Owner:'Luki'}"
    assert "unvalidated, build at own risk" in warnings[0]["message"]


def test_custom_block_without_allowlist_is_error(registry):
    errors, warnings = registry.validate(["mymod:gizmo"])
    assert len(errors) == 1
    assert "allowlist" in errors[0]["message"]
    assert errors[0]["suggestions"] == []  # no vanilla guesses for custom namespaces
    assert warnings == []


def test_air_always_legal(registry):
    errors, warnings = registry.validate(["minecraft:air"])
    assert errors == []
    assert warnings == []


def test_nbt_is_opaque_but_syntax_checked(registry):
    # Valid NBT passes without any schema knowledge of chests.
    errors, _ = registry.validate(
        ['minecraft:chest[facing=north]{Items:[{id:"minecraft:stone",Count:1b}]}']
    )
    assert errors == []
    # Braces inside quoted strings do not count.
    errors, _ = registry.validate(
        ['minecraft:chest{CustomName:\'{"text":"a}b"}\'}']
    )
    assert errors == []
    # Unbalanced NBT is an error.
    errors, _ = registry.validate(["minecraft:chest{Items:[{id:stone}"])
    assert len(errors) == 1
    assert "unbalanced" in errors[0]["message"]


def test_malformed_block_string(registry):
    errors, _ = registry.validate(["minecraft:oak_stairs[facing]"])
    assert len(errors) == 1
    assert "malformed property" in errors[0]["message"]


def test_prefers_blocks_suggest_when_available(monkeypatch, registry):
    mod = types.ModuleType("mcbuilder.blocks")
    mod.suggest = lambda name, candidates: ["minecraft:injected"]
    monkeypatch.setitem(sys.modules, "mcbuilder.blocks", mod)
    assert registry._suggest("minecraft:oak_stair") == ["minecraft:injected"]


def test_suggest_single_arg_fallback(monkeypatch, registry):
    mod = types.ModuleType("mcbuilder.blocks")
    mod.suggest = lambda name: ["minecraft:single"]
    monkeypatch.setitem(sys.modules, "mcbuilder.blocks", mod)
    assert registry._suggest("minecraft:oak_stair") == ["minecraft:single"]


def test_load_missing_registry_raises_helpful_error(tmp_path):
    with pytest.raises(RegistryError, match=r"mcbuild assets fetch --version 99\.9"):
        Registry.load("99.9", tmp_path)


def test_load_reads_normalized_file(tmp_path):
    version_dir = tmp_path / "7.7"
    version_dir.mkdir()
    payload = {
        "version": "7.7",
        "layout": "pc/7.7",
        "blocks": {"minecraft:test_block": {"properties": {"lit": ["true", "false"]}}},
    }
    (version_dir / "minecraft-data.json").write_text(json.dumps(payload))
    reg = Registry.load("7.7", tmp_path)
    assert reg.version == "7.7"
    assert "minecraft:test_block" in reg.names()


def test_load_accepts_raw_minecraft_data_list(tmp_path):
    version_dir = tmp_path / "8.8"
    version_dir.mkdir()
    raw = [
        {"id": 0, "name": "air", "states": []},
        {
            "id": 1,
            "name": "oak_stairs",
            "states": [
                {
                    "name": "facing",
                    "type": "enum",
                    "values": ["north", "south", "west", "east"],
                },
                {"name": "waterlogged", "type": "bool"},
            ],
        },
    ]
    (version_dir / "minecraft-data.json").write_text(json.dumps(raw))
    reg = Registry.load("8.8", tmp_path)
    errors, _ = reg.validate(["minecraft:oak_stairs[facing=north]"])
    assert errors == []
    errors, _ = reg.validate(["minecraft:oak_stairs[facing=up]"])
    assert len(errors) == 1


def test_normalize_block_data_rejects_garbage():
    with pytest.raises(ValueError, match="unrecognized registry data"):
        normalize_block_data({"nope": True})
