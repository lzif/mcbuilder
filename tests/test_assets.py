"""Unit tests for mcbuilder.assets — network is fully monkeypatched out."""

import hashlib
import io
import json
import zipfile

import pytest

from mcbuilder import assets
from mcbuilder.assets import (
    PISTON_MANIFEST,
    _closest_pc_layout,
    _version_key,
    fetch,
)
from mcbuilder.errors import AssetError

RAW_BLOCKS = [
    {"id": 0, "name": "air", "displayName": "Air", "states": []},
    {"id": 1, "name": "stone", "displayName": "Stone", "states": []},
    {
        "id": 2,
        "name": "oak_stairs",
        "displayName": "Oak Stairs",
        "states": [
            {
                "name": "facing",
                "type": "enum",
                "num_values": 4,
                "values": ["north", "south", "west", "east"],
            },
            {"name": "waterlogged", "type": "bool", "num_values": 2},
        ],
    },
]

DATA_PATHS = {
    "pc": {
        "1.21.3": {"blocks": "pc/1.21.3"},
        "1.21.11": {"blocks": "pc/1.21.11"},
        "26.1": {"blocks": "pc/26.1"},
    }
}

VERSION_JSON_URL = "https://example.invalid/version.json"
CLIENT_JAR_URL = "https://example.invalid/client.jar"


def make_fake_jar() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("assets/minecraft/blockstates/stone.json", b'{"variants":{}}')
        zf.writestr("assets/minecraft/models/block/cube_all.json", b"{}")
        zf.writestr("assets/minecraft/textures/block/stone.png", b"\x89PNG\r\n\x1a\n")
        # Must NOT be extracted:
        zf.writestr("META-INF/MANIFEST.MF", b"junk")
        zf.writestr("assets/minecraft/textures/item/stick.png", b"junk")
    return buf.getvalue()


def fake_http_factory(
    jar_bytes,
    *,
    raw_blocks=RAW_BLOCKS,
    data_paths=DATA_PATHS,
    manifest_ids=("26.2",),
    corrupt_jar=False,
):
    def fake(url, timeout=120):
        if url.endswith("/data/pc/26.2/blocks.json"):
            return 404, b"not found"  # 26.2 not in minecraft-data yet
        if url.endswith("/data/dataPaths.json"):
            return 200, json.dumps(data_paths).encode()
        if url.endswith("/data/pc/26.1/blocks.json"):
            return 200, json.dumps(raw_blocks).encode()
        if url == PISTON_MANIFEST:
            versions = [
                {"id": vid, "url": VERSION_JSON_URL} for vid in manifest_ids
            ]
            return 200, json.dumps({"versions": versions}).encode()
        if url == VERSION_JSON_URL:
            return 200, json.dumps(
                {
                    "downloads": {
                        "client": {
                            "url": CLIENT_JAR_URL,
                            "sha1": hashlib.sha1(jar_bytes).hexdigest(),
                        }
                    }
                }
            ).encode()
        if url == CLIENT_JAR_URL:
            return (200, b"corrupted!") if corrupt_jar else (200, jar_bytes)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake


def test_version_key_ordering():
    assert _version_key("26.2") > _version_key("26.1")
    assert _version_key("26.1") > _version_key("1.21.11")
    assert _version_key("26.4") > _version_key("26.4-snapshot-3")
    with pytest.raises(AssetError):
        _version_key("not-a-version")


def test_closest_pc_layout():
    assert _closest_pc_layout("26.2", DATA_PATHS) == "pc/26.1"
    assert _closest_pc_layout("26.1", DATA_PATHS) == "pc/26.1"
    assert _closest_pc_layout("1.21.4", DATA_PATHS) == "pc/1.21.3"
    assert _closest_pc_layout("0.1", DATA_PATHS) is None


def test_fetch_26_2_falls_back_to_26_1_layout(tmp_path, monkeypatch):
    jar_bytes = make_fake_jar()
    monkeypatch.setattr(assets, "_http_get", fake_http_factory(jar_bytes))

    dest = fetch("26.2", tmp_path)
    assert dest == tmp_path / "26.2"

    registry_file = dest / "minecraft-data.json"
    payload = json.loads(registry_file.read_text())
    assert payload["version"] == "26.2"
    assert payload["layout"] == "pc/26.1"  # fallback recorded
    blocks = payload["blocks"]
    assert blocks["minecraft:stone"]["properties"] == {}
    assert blocks["minecraft:oak_stairs"]["properties"]["facing"] == [
        "north",
        "south",
        "west",
        "east",
    ]
    assert blocks["minecraft:oak_stairs"]["properties"]["waterlogged"] == [
        "true",
        "false",
    ]

    client = dest / "client"
    assert (client / "assets/minecraft/blockstates/stone.json").is_file()
    assert (client / "assets/minecraft/models/block/cube_all.json").is_file()
    assert (client / "assets/minecraft/textures/block/stone.png").is_file()
    assert not (client / "META-INF/MANIFEST.MF").exists()
    assert not (client / "assets/minecraft/textures/item/stick.png").exists()


def test_fetch_extracts_version_json_when_present(tmp_path, monkeypatch):
    # The jar root's version.json carries the authoritative DataVersion
    # ("world_version"); the .nbt exporter prefers it over its table.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("assets/minecraft/blockstates/stone.json", b'{"variants":{}}')
        zf.writestr("version.json", json.dumps({"world_version": 4903}).encode())
    monkeypatch.setattr(assets, "_http_get", fake_http_factory(buf.getvalue()))

    dest = fetch("26.2", tmp_path)
    payload = json.loads((dest / "version.json").read_text(encoding="utf-8"))
    assert payload["world_version"] == 4903


def test_fetch_tolerates_jar_without_version_json(tmp_path, monkeypatch):
    # make_fake_jar() has no version.json — extraction must not fail.
    monkeypatch.setattr(assets, "_http_get", fake_http_factory(make_fake_jar()))
    dest = fetch("26.2", tmp_path)
    assert not (dest / "version.json").exists()


def test_fetch_is_idempotent(tmp_path, monkeypatch):
    jar_bytes = make_fake_jar()
    monkeypatch.setattr(assets, "_http_get", fake_http_factory(jar_bytes))
    fetch("26.2", tmp_path)

    def boom(url, timeout=120):
        raise AssertionError("network called despite warm cache")

    monkeypatch.setattr(assets, "_http_get", boom)
    dest = fetch("26.2", tmp_path)  # must not touch the network
    assert dest == tmp_path / "26.2"


def test_fetch_raises_when_version_not_in_minecraft_data(tmp_path, monkeypatch):
    jar_bytes = make_fake_jar()
    monkeypatch.setattr(
        assets, "_http_get", fake_http_factory(jar_bytes, data_paths={"pc": {}})
    )
    with pytest.raises(AssetError, match="not in PrismarineJS/minecraft-data yet"):
        fetch("26.2", tmp_path)


def test_fetch_raises_when_version_not_in_piston(tmp_path, monkeypatch):
    jar_bytes = make_fake_jar()
    monkeypatch.setattr(
        assets, "_http_get", fake_http_factory(jar_bytes, manifest_ids=())
    )
    with pytest.raises(AssetError, match="not found in Mojang's version manifest"):
        fetch("26.2", tmp_path)


def test_fetch_rejects_corrupt_jar(tmp_path, monkeypatch):
    jar_bytes = make_fake_jar()
    monkeypatch.setattr(
        assets, "_http_get", fake_http_factory(jar_bytes, corrupt_jar=True)
    )
    with pytest.raises(AssetError, match="sha1 verification"):
        fetch("26.2", tmp_path)
