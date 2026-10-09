# mcbuilder

Python tooling for AI agents that build Minecraft structures. Make it easier
for agents to build complex structures while reducing code complexity —
without reducing detail.

The loop: an agent writes a builder script → mcbuilder validates every block
against the real block registry → renders labeled preview images from
customizable angles → the agent iterates on what it sees. `report.json`'s
`block_counts` is your survival material shopping list.

> **Deploy artifact: `.nbt`.** `mcbuild run` writes a vanilla structure-block
> `.nbt` (gzipped NBT) next to `report.json` — the same shape a structure
> block saves, readable by LostQoL's structure parser. More serializers
> (`.mcstructure`, `.schem`, ...) plug in as swappable exporters; the DSL,
> validator, parts catalog, preview renderer, and CLI are format-agnostic.

## Install

```bash
pip install mcbuilder
# or with uv:
uv pip install mcbuilder
```

Python 3.10+.

## Quick start

```bash
mcbuild assets fetch --version 1.21.4   # one-time: registry + vanilla textures
```

```python
# hut.py
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["az045_el025", "top"])

with BUILD:
    BUILD.box((0, 0, 0), (9, 3, 9), "minecraft:stone_bricks")
    BUILD.walls((0, 4, 0), (9, 7, 9), "minecraft:mossy_stone_bricks")
    BUILD.stairs_run((0, 0, 10), "north", 5, "minecraft:stone_brick_stairs")
```

```bash
mcbuild check hut.py          # validate only, fast
mcbuild run hut.py --out dist/ --preview
```

`mcbuild run` writes an auto-versioned `dist/run-001/` directory with
`report.json` (errors with file:line provenance, warnings, block counts,
labeled view list), and `previews/` PNGs.

## Parts catalog

The agent does composition and proportion; the parts own the geometry
math. Every part is called as `mb.parts.<name>(BUILD, ...)` inside the
`with BUILD:` block — or via the `BUILD.<name>(...)` delegates
(`BUILD.stairs_run(...)`, `BUILD.pillar(...)`, `BUILD.railing(...)`).

| Part | Signature | Facing rule |
|---|---|---|
| `stairs_run` | `(BUILD, start, direction, length, block, width=1)` | ascends *towards* `direction`; pass the stair block **without** a `facing` property — the part sets it |
| `pillar` | `(BUILD, base, height, block)` | vertical stack at `base`, no facing involved |
| `railing` | `(BUILD, start, end, block)` | straight axis-aligned run (x or z constant, same y); fence/wall connections resolve in-game, previews show unconnected arms |
| `roof_gable` | `BUILD.roof_gable(c1, c2, block, ridge=)` | `ridge="x"` or `"z"` (required keyword); pass the stair block **without** `facing` |

Core DSL methods on `BUILD`: `set(x, y, z, block)`, `box(c1, c2, block)`,
`walls(c1, c2, block)`, `floor(c1, c2, block)`. Block strings are canonical
`minecraft:name[prop=val,...]{nbt}` — property order never matters.

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
