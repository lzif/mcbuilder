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

### Instancing: define once, stamp many

`mb.part.*` factories return a `Geometry` — pure relative-coordinate
voxel data that places nothing. Stamp it with `BUILD.place()`:

```python
import mcbuilder as mb

pillar = mb.part.pillar(height=5, block="minecraft:oak_log")  # defines, places nothing

with BUILD:
    BUILD.place(pillar, at=(0, 0, 0))
    BUILD.place(pillar, at=(8, 0, 0))
    BUILD.place(pillar, at=(0, 0, 8))
    BUILD.place(pillar, at=(8, 0, 8))
```

Factories (`mb.part.box/pillar/stairs_run/railing`) are keyword-only;
`BUILD.place(geo, at=(x, y, z))` takes explicit coordinates every time
(no implicit placement state). Geometries compose: `geo1 + geo2`
stamps as one unit (later wins on overlap). For custom shapes, build a
datablock cell by cell: `g = mb.Geometry(); g.set(dx, dy, dz, block)`.

## Previews

`mcbuild run --preview` renders two tiers into each run dir:

- `previews/` — fast tier: textured cubes, quick to iterate on.
  Flagged `directions_untrusted` in `report.json`: it cannot show
  facing/axis state, so never trust a direction from it.
- `previews_trusted/` — direction-trusted tier: simplified geometry
  that shows orientation truthfully (stairs as oriented wedges,
  slabs as half-boxes, axis bands on logs, facing plates, …), no
  textures needed. Flagged `directions_trusted`. Blocks it cannot
  render truthfully become labeled cubes plus one warning per block
  type — check `report.json` warnings before shipping an `.nbt`.

## Rotation semantics

`mcbuilder.rotation` implements the structure rotation table
(`rotate_position`, `rotate_blockstate` for `NONE` / `CLOCKWISE_90` /
`CLOCKWISE_180` / `COUNTERCLOCKWISE_90`) — the same semantics the
LostQoL `StructurePaster` applies server-side, so a design verified
here pastes correctly at all four rotations.

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
