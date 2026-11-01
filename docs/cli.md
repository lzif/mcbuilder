# CLI

```
mcbuild init [path] [--force]       write a starter build script
mcbuild check <script>              validate only
mcbuild run <script> [options]      validate, export .nbt, render previews, write a guide
mcbuild diff <run_a> <run_b>        what changed between two runs
mcbuild import <file.nbt>           turn an existing structure into a builder script
mcbuild assets fetch --version V    download the block registry and vanilla assets
```

Every command that takes a script finds `mcbuild.toml` by walking up from the script's folder
(`--config PATH` overrides). Exit code is `1` when validation fails.

## `mcbuild check`

```
house.py — OK (1885 blocks, 69 types, 0 errors, 0 warnings)
```

Runs the script, then checks every distinct block against the registry of `mc_version`: the
name, each property name and each property value. Errors carry the script line that placed the
block and the closest valid names. Warnings cover allowlisted custom blocks and scripts that
import `random` directly (use `BUILD.rng()` so the same seed always gives the same build).

## `mcbuild run`

```bash
mcbuild run house.py --preview --guide
```

```
run dir: dist/run-001
  1885 blocks, 69 types, dims 19x22x17 — 0 errors, 0 warnings, 311 placements overwritten
  faithful previews: 3 in previews_faithful/
  artifact: house.nbt (nbt, DataVersion 4903)
  guide: guide/guide.md
```

Each run writes a new numbered folder, so earlier runs stay around for `diff`.

| Flag | Default | Meaning |
|---|---|---|
| `--out DIR` | `dist/` | where `run-NNN/` folders go |
| `--preview` | off | render previews ([previews](previews.md)) |
| `--tier T` | `faithful` | `faithful`, `trusted`, `fast` or `all` |
| `--views SPEC` | script's views | cameras, e.g. `"iso;az200_el025;top"` |
| `--count N` | | add an `N`-view orbit |
| `--focus X0,Y0,Z0:X1,Y1,Z1` | | render only this box (the `.nbt` is still the whole build) |
| `--guide` | off | write the layer-by-layer build guide |
| `--air MODE` | `none` | which air goes into the `.nbt`, see below |

Nothing is exported or rendered when validation fails.

### The `.nbt`

`<script>.nbt` in the run folder is a vanilla structure file (gzipped NBT with `DataVersion`,
`size`, `palette`, `blocks`). Load it with a structure block, Litematica or a server-side paster.
It is byte-for-byte reproducible: the same script and seed always produce the same file.

`DataVersion` comes from `mc_version`, so pin the version your world runs.

**Air** (`--air`):

| Mode | Writes | Pasting it… |
|---|---|---|
| `none` | no air | only adds blocks; everything else in the world stays |
| `explicit` | cells you set to `"minecraft:air"` | also clears those cells: interiors cut into terrain, air pockets under water |
| `all` | every cell of the bounding box that has no block | clears the whole box |

Use `explicit` for an underwater base: the interior air pushes the water out, the ocean around
it stays.

### The build guide

`--guide` writes `guide/` into the run folder: `guide.md` with the full material list (in stacks
of 64) and, per layer from the bottom up, a top-down plan image and that layer's materials. In
the plans, north is up, the layer below is shown faded, arrows show `facing`, bars show
`axis=x/z` and `T` marks top-half blocks. Coordinates count from the build's north-west bottom
corner, the same origin as the `.nbt`.

### `report.json`

| Key | |
|---|---|
| `errors`, `warnings` | `{"message", "at", "suggestions", ...}` |
| `block_counts` | blockstate → count, air excluded |
| `dimensions` | `{"x", "y", "z"}` of the exported box |
| `origin` | script coordinates of the `.nbt`'s `[0, 0, 0]` |
| `views` | each preview file with its camera and tier flags (`directions_trusted` / `directions_untrusted`) |
| `artifacts` | the `.nbt` (and guide) written |
| `overwritten_placements` | how many times a block replaced a different block; a sudden jump usually means two parts overlap by mistake |

## `mcbuild diff`

```bash
mcbuild diff run-001 run-002          # or just: mcbuild diff 001 002
```

Lists added, removed and replaced cells (in script coordinates, so moving one part doesn't make
everything look changed) and writes a side-by-side image when both runs rendered the same view.
`--max N` limits the list. Exit code `1` when the runs differ, like `diff(1)`.

## `mcbuild import`

```bash
mcbuild import tavern.nbt                 # writes tavern.py next to it
mcbuild import tavern.nbt -o study/tavern.py --keep-air
```

Reads a structure-block `.nbt` (convert `.schem` / `.litematic` to `.nbt` first) and writes a
script that rebuilds it exactly:

- a header with the size, block counts per type and blocks per layer, for studying the build;
- one named constant per block state (`OAK_STAIRS_N_BOTTOM = "minecraft:oak_stairs[...]"`),
  most used first;
- runs of the same block merged into `BUILD.box(...)`, single blocks as `BUILD.set(...)`,
  grouped by layer from the bottom up.

Coordinates start at the structure's north-west bottom corner. Air is left out unless
`--keep-air`; `structure_void` is always left out. Block-entity data (chest contents, sign text)
and entities are not carried over; the header says how many were dropped. `--force` overwrites
an existing script.

## `mcbuild assets fetch`

```bash
mcbuild assets fetch --version 26.2 [--cache-dir DIR] [--force]
```

Downloads the block registry and the vanilla client assets (models, blockstates, textures) into
`~/.cache/mcbuilder/<version>/`. Needed once per version.

## `mcbuild.toml`

```toml
mc_version = "26.2"                  # registry, textures and DataVersion
max_dimensions = [256, 256, 256]     # size limit per axis
allowlist = ["mymod:custom_block"]   # custom blocks: pass validation with a warning
# assets_dir = "/elsewhere"          # default ~/.cache/mcbuilder/<mc_version>/
```
