"""Generate docs/views-gallery/ : 6 standard views of a tiny hut.

Hermetic (no network): reuses the fake vanilla asset tree from
tests/test_preview_faithful.py (make_assets) plus a cube-all `test:planks`
blockstate/model added here. Renders with the faithful tier
(presentation look), one PNG per view.

Usage:
    cd ~/workspace/mcbuilder && .venv/bin/python /tmp/gen_views_gallery.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent  # docs/views-gallery
REPO = Path.home() / "workspace" / "mcbuilder"
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "src"))

from test_preview_faithful import _write_json, _write_tex, make_assets  # noqa: E402

import mcbuilder as mb  # noqa: E402
from mcbuilder import preview_faithful as pf  # noqa: E402
from mcbuilder.views import parse_views  # noqa: E402

# The 6 standard gallery views: 4 cardinal low-angle views + top + iso.
VIEWS_SPEC = "az000_el025;az090_el025;az180_el025;az270_el025;top;iso"


def add_planks_assets(root: Path) -> None:
    """Cube-all `test:planks` blockstate + model, wired to make_assets' texture."""
    mc = root / "client" / "assets" / "minecraft"
    bs_dir = mc / "blockstates"
    models_dir = mc / "models" / "block"
    faces = {
        f: {"uv": [0, 0, 16, 16], "texture": "#all"}
        for f in ("up", "down", "north", "south", "west", "east")
    }
    _write_json(models_dir / "test_planks.json", {
        "textures": {"all": "minecraft:block/test_planks"},
        "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": faces}],
    })
    _write_json(bs_dir / "test_planks.json", {
        "variants": {"": {"model": "minecraft:block/test_planks"}},
    })
    assert (mc / "textures" / "block" / "test_planks.png").is_file()


def build_hut():
    """Tiny 7x7 hut: plank floor + walls, gable roof of fake stairs."""
    b = mb.Build(seed=1)
    with b:
        b.floor((0, 0, 0), (6, 0, 6), "test:test_planks")
        b.walls((0, 1, 0), (6, 3, 6), "test:test_planks")
        b.roof_gable((0, 3, 0), (6, 3, 6), "test:test_stairs", "x")
    return b.grid


def main() -> None:
    assets_root = Path("/tmp/views-gallery-assets")
    make_assets(assets_root)
    add_planks_assets(assets_root)

    grid = build_hut()
    views = parse_views(VIEWS_SPEC)
    assert [v.label for v in views] == [
        "az000_el025", "az090_el025", "az180_el025", "az270_el025", "top", "iso",
    ]

    out_dir = REPO / "docs" / "views-gallery"
    res = pf.render(grid, out_dir, views, assets_root,
                    presentation=True, title="Sample hut")
    for p in res:
        print(p, p.stat().st_size, "bytes")
    assert not res.info.get("untrusted_blocks"), res.info
    print("untrusted:", res.info.get("untrusted_blocks"))


if __name__ == "__main__":
    main()
