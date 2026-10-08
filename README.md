# mcbuilder

Python tooling for AI agents that build Minecraft structures. Make it easier
for agents to build complex structures while reducing code complexity —
without reducing detail.

The loop: an agent writes a builder script → mcbuilder validates every block
against the real block registry → exports `.litematic` (plus `.schem`,
`.nbt`, `.mcfunction`) → renders labeled preview images from customizable
angles → the agent iterates on what it sees. Then load the `.litematic` in
Litematica and build it in survival, guided by the hologram.

## Install

```bash
pip install mcbuilder
# or with uv:
uv pip install mcbuilder
```

Python 3.10+.

## Quick start

```python
# waystone.py
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["orbit:8_el:25", "top"])

with BUILD:
    BUILD.box((0, 0, 0), (9, 3, 9), "minecraft:stone_bricks")
    BUILD.walls((0, 4, 0), (9, 7, 9), "minecraft:mossy_stone_bricks")
    BUILD.stairs_run((0, 0, 10), "north", 5, "minecraft:stone_brick_stairs")
```

```bash
mcbuild check waystone.py          # validate only, fast
mcbuild run waystone.py --out dist/ --preview
```

`mcbuild run` writes an auto-versioned `dist/run-001/` directory with the
exported files, `report.json` (errors with file:line provenance, warnings,
block counts, labeled view list), and `previews/` PNGs.

Then load `waystone.litematic` in Litematica (client-side mod) and build it
in survival following the hologram. `report.json`'s `block_counts` doubles
as your material shopping list.

## Block versions

`mcbuild assets fetch --version <x.y.z>` downloads the block registry and
vanilla client assets for your server's version into the local cache.
Mojang assets are never bundled with this package — they are fetched at
user time. Pin the version per project in `mcbuild.toml`:

```toml
mc_version = "1.21.4"
max_dimensions = [256, 256, 256]
allowlist = ["mymod:custom_block"]
```

## License

MIT — see [LICENSE](LICENSE).
