"""Make the in-repo mcbuilder package importable for tests (no install needed).

Also hosts the shared fake-asset fixtures used by the preview-tier tests
(moved from tests/test_preview_faithful.py — behavior identical).
"""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# fake assets
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def _write_tex(path: Path, color):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path)


def make_assets(root: Path) -> Path:
    """Minimal fake vanilla asset tree with a stair-like model.

    ``test_stairs`` mirrors the vanilla convention verified 2026-10-09:
    the unrotated model has its tall element at +X and maps to
    facing=east; y rotations run clockwise viewed from above.
    """
    mc = root / "client" / "assets" / "minecraft"
    bs_dir = mc / "blockstates"
    models_dir = mc / "models" / "block"
    tex_dir = mc / "textures" / "block"

    _write_tex(tex_dir / "test_planks.png", (150, 100, 50))

    # Base stair geometry: slab + tall element at +X (east half).
    _write_json(models_dir / "test_stairs_base.json", {
        "textures": {"side": "minecraft:block/test_planks",
                     "top": "minecraft:block/test_planks",
                     "bottom": "minecraft:block/test_planks"},
        "elements": [
            {"from": [0, 0, 0], "to": [16, 8, 16],
             "faces": {
                 "up": {"uv": [0, 0, 16, 16], "texture": "#top"},
                 "down": {"uv": [0, 0, 16, 16], "texture": "#bottom"},
                 "north": {"uv": [0, 8, 16, 16], "texture": "#side"},
                 "south": {"uv": [0, 8, 16, 16], "texture": "#side"},
                 "west": {"uv": [0, 8, 16, 16], "texture": "#side"},
                 "east": {"uv": [0, 8, 16, 16], "texture": "#side"},
             }},
            {"from": [8, 8, 0], "to": [16, 16, 16],
             "faces": {
                 "up": {"uv": [8, 0, 16, 16], "texture": "#top"},
                 "north": {"uv": [0, 0, 8, 8], "texture": "#side"},
                 "south": {"uv": [8, 0, 16, 8], "texture": "#side"},
                 "west": {"uv": [0, 0, 16, 8], "texture": "#side"},
                 "east": {"uv": [0, 0, 16, 8], "texture": "#side"},
             }},
        ],
    })
    _write_json(models_dir / "test_stairs.json", {
        "parent": "minecraft:block/test_stairs_base",
    })
    _write_json(bs_dir / "test_stairs.json", {
        "variants": {
            "facing=east": {"model": "minecraft:block/test_stairs"},
            "facing=south": {"model": "minecraft:block/test_stairs",
                             "y": 90},
            "facing=west": {"model": "minecraft:block/test_stairs",
                            "y": 180},
            "facing=north": {"model": "minecraft:block/test_stairs",
                             "y": 270},
            "facing=east,half=top": {"model": "minecraft:block/test_stairs",
                                     "x": 180},
        }
    })

    # Multipart block: two cases, one conditional.
    _write_tex(tex_dir / "test_post.png", (100, 100, 100))
    _write_json(models_dir / "test_post.json", {
        "textures": {"all": "minecraft:block/test_post"},
        "elements": [
            {"from": [6, 0, 6], "to": [10, 16, 10],
             "faces": {f: {"uv": [0, 0, 16, 16], "texture": "#all"}
                       for f in ("up", "down", "north", "south",
                                 "west", "east")}},
        ],
    })
    _write_json(models_dir / "test_arm.json", {
        "textures": {"all": "minecraft:block/test_post"},
        "elements": [
            {"from": [10, 6, 6], "to": [16, 10, 10],
             "faces": {f: {"uv": [0, 0, 16, 16], "texture": "#all"}
                       for f in ("up", "down", "north", "south",
                                 "west", "east")}},
        ],
    })
    _write_json(bs_dir / "test_multi.json", {
        "multipart": [
            {"apply": {"model": "minecraft:block/test_post"}},
            {"when": {"arm": "true"},
             "apply": {"model": "minecraft:block/test_arm"}},
            {"when": {"OR": [{"arm": "false"}, {"arm": "maybe"}]},
             "apply": {"model": "minecraft:block/test_post"}},
        ]
    })
    # -- biome-tint fakes (gap1): solid-color textures, hermetic ----------
    def _full_cube_faces(tex, tintindex=None):
        faces = {}
        for f in ("up", "down", "north", "south", "west", "east"):
            face = {"uv": [0, 0, 16, 16], "texture": tex}
            if tintindex is not None:
                face["tintindex"] = tintindex
            faces[f] = face
        return faces

    def _cube_model(name, tex_var, tex_color, tintindex):
        _write_tex(tex_dir / f"{tex_var}.png", tex_color)
        _write_json(models_dir / f"{name}.json", {
            "parent": "minecraft:block/cube_all",
            "textures": {"all": f"test:block/{tex_var}"},
            "elements": [
                {"from": [0, 0, 0], "to": [16, 16, 16],
                 "faces": _full_cube_faces("#all", tintindex)},
            ],
        })
        _write_json(bs_dir / f"{name}.json", {
            "variants": {"": {"model": f"test:block/{name}"}},
        })

    # leaves analog: tintindex 0, table entry injected per-test.
    _cube_model("test_tint_cube", "tint_gray", (200, 200, 200), 0)
    # same texture file, different block (per-block table lookup pin).
    _write_json(bs_dir / "test_tint_cube_b.json", {
        "variants": {"": {"model": "test:block/test_tint_cube"}},
    })
    # wildflowers/flowerbed analog: tintindex 1 must still tint.
    _cube_model("test_tint_index1", "tint_gray1", (170, 170, 170), 1)
    # cherry-leaves analog: tintindex 0 inherited from parent, but the
    # block itself has no table entry -> default-deny, untinted.
    _write_tex(tex_dir / "tint_cherry.png", (180, 140, 140))
    _write_json(models_dir / "test_tint_cherry_parent.json", {
        "textures": {"all": "test:block/tint_cherry"},
        "elements": [
            {"from": [0, 0, 0], "to": [16, 16, 16],
             "faces": _full_cube_faces("#all", 0)},
        ],
    })
    _write_json(models_dir / "test_tint_cherry.json", {
        "parent": "test:block/test_tint_cherry_parent",
    })
    _write_json(bs_dir / "test_tint_cherry.json", {
        "variants": {"": {"model": "test:block/test_tint_cherry"}},
    })
    # untinted control: real texture, no tintindex, no table entry.
    _cube_model("test_tint_plain", "tint_plain", (120, 120, 120), None)

    # grass-block analog: element 0 north = untinted #side,
    # element 1 north = tinted #overlay -> two world-north quads.
    _write_tex(tex_dir / "tint_side.png", (210, 210, 210))
    _write_tex(tex_dir / "tint_overlay.png", (160, 160, 160))
    _write_json(models_dir / "test_tint_overlay.json", {
        "textures": {"side": "test:block/tint_side",
                     "overlay": "test:block/tint_overlay"},
        "elements": [
            {"from": [0, 0, 0], "to": [16, 16, 16],
             "faces": {"north": {"uv": [0, 0, 16, 16],
                                 "texture": "#side"}}},
            {"from": [0, 0, 0], "to": [16, 16, 16],
             "faces": {"north": {"uv": [0, 0, 16, 16],
                                 "texture": "#overlay",
                                 "tintindex": 0}}},
        ],
    })
    _write_json(bs_dir / "test_tint_overlay.json", {
        "variants": {"": {"model": "test:block/test_tint_overlay"}},
    })

    # bamboo analog: first apply untinted (stalk), second apply tinted
    # (leaves) — fast tier resolves only the first apply.
    _cube_model("test_stalk", "tint_stalk", (140, 140, 140), None)
    _cube_model("test_leaf", "tint_leaf", (150, 150, 150), 0)
    _write_json(bs_dir / "test_tint_multi.json", {
        "multipart": [
            {"apply": {"model": "test:block/test_stalk"}},
            {"apply": {"model": "test:block/test_leaf"}},
        ],
    })
    return mc


@pytest.fixture()
def assets_root(tmp_path):
    return make_assets(tmp_path)


@pytest.fixture()
def tex_cache():
    return {}
