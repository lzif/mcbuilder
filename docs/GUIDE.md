# mcbuilder — User Guide

Author structures in Python, validate them against the real Minecraft
block registry, preview them, and export a vanilla structure `.nbt`
ready for the LostQoL plugin pipeline.

The loop:

```
write script → mcbuild check → mcbuild run --preview → iterate
→ .nbt → LostQoL resources → server-side paste
```

## 1. Installation

Python 3.10+.

```bash
pip install mcbuilder
# or:
uv pip install mcbuilder
```

Then fetch the block registry and vanilla client assets **once** for
your server's Minecraft version (Mojang assets are never bundled —
they are downloaded at user time into `~/.cache/mcbuilder/`).
Textures are part of the fetch by default — there is no separate
textures step:

```bash
mcbuild assets fetch --version 26.2
```

Pin the version per project in `mcbuild.toml` (discovered from the
script's directory; `--config` overrides):

```toml
mc_version = "26.2"
max_dimensions = [256, 256, 256]
allowlist = ["lostqol:waystone"]
# assets_dir = "/custom/cache"   # optional; default ~/.cache/mcbuilder/<mc_version>/
```

## 2. Five-minute house — just build something

Skip the architecture chapter for now. This is the whole loop:
write direct calls, `check`, `run --preview`, look at the pictures,
tweak, repeat. No factories, no shared modules — one asymmetric,
one-off build:

```python
# house.py
import mcbuilder as mb

BUILD = mb.Build(seed=1)

with BUILD:
    # floor + walls: 7 x 5 footprint, walls 3 high
    BUILD.floor((0, 0, 0), (6, 0, 4), "minecraft:cobblestone")
    BUILD.walls((0, 1, 0), (6, 3, 4), "minecraft:oak_planks")

    # doorway (north wall) + window (south wall): carve with air, hang the door
    BUILD.box((3, 1, 0), (3, 2, 0), "minecraft:air")
    BUILD.box((1, 2, 4), (2, 2, 4), "minecraft:air")
    BUILD.set(3, 1, 0, "minecraft:oak_door[facing=north,half=lower,hinge=left]")
    BUILD.set(3, 2, 0, "minecraft:oak_door[facing=north,half=upper,hinge=left]")

    # gable roof: ridge along x, 1-block overhang, eaves at y=4.
    # Span is 7 deep (z -1..5), so it rises ceil(7/2) = 4 above the eaves.
    roof = BUILD.roof_gable(
        (-1, 4, -1), (7, 4, 5), "minecraft:spruce_stairs", ridge="x"
    )

    # chimney sized from the roof's ACTUAL peak — no guessing, no source-diving:
    (_, _, _), (_, peak, _) = roof.bounds()
    BUILD.box((5, peak - 1, 1), (5, peak + 2, 1), "minecraft:cobblestone")
```

```bash
mcbuild check house.py
# house.py — OK (159 blocks, 7 types, 0 errors, 0 warnings)

mcbuild run house.py --preview
# previews land in run-001/previews*/ — look, tweak the numbers, re-run.
```

Two things to notice: `BUILD.roof_gable(...)` **returns the `Geometry`
it placed**, so `roof.bounds()` tells you the real peak instead of you
computing `ceil(span/2)` by hand (§3's dimensions table lists every
helper's output size). And the loop is the whole workflow — the waystone
factory pattern in §4 exists for *repeated* stamping; for a one-off
build, direct calls win.

## 3. Core concepts

### `Build` — the accumulator

Every script defines a module-level `BUILD` and places blocks inside
the required `with BUILD:` batch scope. Placements outside the scope
raise a clean error.

```python
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["iso", "top"])

with BUILD:
    BUILD.set(0, 0, 0, "minecraft:stone_bricks")
```

- `seed` — the **sole** RNG source, exposed as `BUILD.rng()`. Same
  script + same seed ⇒ same grid. The CLI also pins `PYTHONHASHSEED`,
  and warns if your script imports raw `random` / `numpy.random`.
- `views` — preview camera config (see §6). Pure config, no side effects.
- `max_dimensions` — grid bounds; exceeding them raises `GridBoundsError`.
- Provenance — every palette entry records the `file:line` of the
  script call that placed it (first placement wins). Validation
  errors point at your code, not library internals.
- `BUILD.validate(registry, allowlist=())` — explicit validation entry
  point for library/harness users (the CLI calls it once per run;
  it is deliberately *not* run at `__exit__`).
- `BUILD.recenter()` — shift the XZ bbox center to the origin (Y
  untouched). Call after placements, before render/export.

### `Geometry` — datablocks (define once, stamp many)

`mb.part.*` factories return a `Geometry`: pure relative-coordinate
voxel data that places **nothing**. Stamp it with `BUILD.place()`:

```python
pillar = mb.part.pillar(height=5, block="minecraft:oak_log")  # defines, places nothing

with BUILD:
    BUILD.place(pillar, at=(0, 0, 0))
    BUILD.place(pillar, at=(8, 0, 0))
    BUILD.place(pillar, at=(0, 0, 0))  # same instance, stamped twice — fine
```

- All `mb.part.*` signatures are **keyword-only**.
- `BUILD.place(geo, at=(x, y, z))` — `at` has no default and there is
  no placement cursor: explicit coordinates every time.
- Geometries compose: `geo1 + geo2` stamps as one unit (later cells win
  on overlap — same last-write-wins rule as `set`).
- Escape hatch for custom shapes: build a datablock cell by cell.

```python
g = mb.Geometry()
g.set(0, 0, 0, "minecraft:gold_block")
g.set(1, 0, 0, "minecraft:gold_block")
```

### Parts vs one-shots

`mb.parts.*` are one-shot imperative functions — sugar over the
datablock layer (`mb.parts.stairs_run(BUILD, ...)` ≡
`BUILD.place(mb.part.stairs_run(...), at=start)`). Use factories
directly when you stamp something more than once.

Every one-shot helper **returns the `Geometry` it placed** (absolute
coordinates), so `geo.bounds()` tells you exactly what landed — size
the next piece around it instead of guessing:

```python
roof = BUILD.roof_gable((0, 5, 0), (6, 5, 4), "minecraft:spruce_stairs", ridge="x")
(_, _, _), (_, peak, _) = roof.bounds()
BUILD.box((3, peak - 1, 2), (3, peak + 2, 2), "minecraft:cobblestone")  # chimney through the roof
```

| Part | Factory signature | One-shot |
|---|---|---|
| `stairs_run` | `mb.part.stairs_run(*, direction, length=None, block, width=1, target=None)` | `mb.parts.stairs_run(BUILD, start, direction, length=None, block, width=1, *, target=None)` / `BUILD.stairs_run(start, direction, length=None, block, width=1, *, target=None)` |
| `pillar` | `mb.part.pillar(*, height, block)` | `BUILD.pillar(base, height, block)` |
| `railing` | `mb.part.railing(*, start, end, block)` | `BUILD.railing(start, end, block)` |
| `box` | `mb.part.box(*, c1, c2, block)` | `BUILD.box(c1, c2, block)` |

### Output bounds — how big is the thing you just placed?

No helper is a black box. Every entry below is verified against the
implementation; `geo.bounds()` on the returned `Geometry` reports the
same numbers at runtime.

| Helper | Footprint | Height / extent |
|---|---|---|
| `BUILD.box(c1, c2, block)` | XZ rectangle of the corners | `\|dx\|+1` × `\|dy\|+1` × `\|dz\|+1` cells, corners inclusive |
| `BUILD.walls(c1, c2, block)` | same XZ as `box` | four vertical walls over the full Y range; **no** floor, **no** ceiling |
| `BUILD.floor(c1, c2, block)` | XZ rectangle of the corners | 1 thick, at `min(c1.y, c2.y)` |
| `BUILD.roof_gable(c1, c2, block, ridge, eave_height=None)` | XZ rectangle of the corners | rises `ceil(span/2)` above the eave height (`min(c1.y, c2.y)` when `eave_height` is omitted — the corners' Y only sets the eaves), where `span` is the footprint extent **perpendicular** to the ridge (Z extent for `ridge="x"`, X extent for `ridge="z"`). 5-deep ⇒ 3 tall; 6-deep ⇒ 3 tall, no ridge row |
| `BUILD.stairs_run(start, direction, length, block, width=1)` | `length` steps toward `direction` × `width` wide (perpendicular, positive side) | step `i` at `start_y + i`: total rise = `length` |
| `BUILD.stairs_run(start, direction, block, target=(x,y,z))` | same, but the TOP step lands exactly at `target` — no landing math | length derived as `target_y - start_y + 1`; `ValueError` if `target` isn't reachable (must be on the 1:1 diagonal from `start` toward `direction`: zero perpendicular offset, horizontal travel == rise, rise ≥ 0). `length` and `target` are mutually exclusive |
| `BUILD.pillar(base, height, block)` | 1 × 1 at `base` | `height` blocks up from `base.y` |
| `BUILD.railing(start, end, block)` | straight run `start` → `end`, inclusive, axis-aligned | 1 thick |
| `BUILD.place(geo, at=(x,y,z))` | `geo`'s cells shifted by `at` | — |
| `BUILD.set(x, y, z, block)` | one block | — (returns `None`; the primitive, not a helper) |
| `BUILD.carve(c1, c2)` | XZ rectangle of the corners | removes `\|dx\|+1` × `\|dy\|+1` × `\|dz\|+1` cells, corners inclusive, any order — the exact complement of `box` |

### Introspection — reading the build back

Scripts can read their own grid without dropping to numpy. All three
are read-only (no `with BUILD:` needed):

- `BUILD.get(x, y, z)` → the canonical block string at that cell, e.g.
  `"minecraft:oak_stairs[facing=north]"`, or `None` when the cell is
  empty or carved air.
- `BUILD.count(block)` → how many cells hold `block` (exact match on
  the canonical blockstate — the input is canonicalized first, so
  property order never matters, but the property set must match
  verbatim).
- `BUILD.find(block)` → sorted list of `(x, y, z)` tuples holding
  `block`; `[]` when nothing matches.

```python
with BUILD:
    BUILD.box((0, 0, 0), (9, 0, 9), "minecraft:stone")

BUILD.get(0, 0, 0)                    # "minecraft:stone"
BUILD.get(5, 5, 5)                    # None — never placed
BUILD.count("minecraft:stone")        # 100
BUILD.find("minecraft:dirt")          # []
```

**`to_dense()` axis convention** — the trap to avoid. `BUILD.grid.to_dense()`
returns `(array, palette, provenance)` where `array` has shape
`(sx, sy, sz)` and `array[i, j, k]` is the cell at `(minx+i, miny+j, minz+k)`:
**axis 0 is X, axis 1 is Y, axis 2 is Z — the mapping is direct, not
transposed.** Never index `array[z, y, x]`; never assume the first axis is
height. Never-placed cells inside the bbox read as `-1` (`UNSET`);
explicitly carved `"minecraft:air"` cells read as air's palette index
(carved air is distinguishable from untouched cells — that's what the
exporter's `include_air` flag needs). Explicit air also expands the dense
bounds: an air cell outside the non-air region grows the `to_dense()` array
instead of crashing it.

Subtractive primitive: `BUILD.carve(c1, c2)` removes every cell in the
inclusive box between the two corners (any order — same corner
semantics as `box`). Removed cells read as unset (`UNSET` in
`to_dense`, `None` from `get`), unlike `set(x, y, z, "minecraft:air")`
which leaves a carved air cell the exporter can include. Carving a
region with no placed cells is a no-op. `carve` is a mutation, so it
requires `with BUILD:`.

### Layering law

```
voxels.VoxelGrid.place   raw cells, no canonicalization        (bmesh layer)
Build.set                canonicalize + provenance             (op layer)
Geometry / mb.part.*     pure data, no Build, no placement    (datablock layer)
Build.place              stamp a Geometry into the grid        (op layer)
mb.parts.*               one-shot sugar over place()           (op layer)
your script              the modifier stack (re-run = re-evaluate)
```

### Stairs by target, not landing math

`stairs_run` accepts `target=` — the exact cell the TOP step must
occupy — instead of a hand-computed `length`:

```python
with BUILD:
    # top step lands exactly at (4, 3, 0): 4 steps, no math
    BUILD.stairs_run((0, 0, 0), "east", block="minecraft:oak_stairs",
                     target=(4, 3, 0))
```

The length is derived as `target_y - start_y + 1`, and `target` must
sit on the run's 1:1 diagonal from `start` toward `direction` (zero
perpendicular offset, horizontal travel equal to the rise, rise ≥ 0)
— otherwise `ValueError`. `length` and `target` are mutually
exclusive: give exactly one.

## 4. Authoring walkthrough

A tiny stone hut, start to finish. Save as `hut.py`:

```python
import mcbuilder as mb

BUILD = mb.Build(seed=7, views=["iso", "top"])

with BUILD:
    # 5x5 floor, one block thick
    BUILD.floor((0, 0, 0), (4, 0, 4), "minecraft:stone_bricks")
    # hollow walls, 3 high (no floor, no ceiling)
    BUILD.walls((0, 1, 0), (4, 3, 4), "minecraft:cobblestone")
    # gable roof: ridge runs along x, eaves at the z extremes.
    # pass stairs WITHOUT facing — the helper computes it.
    BUILD.roof_gable((0, 4, 0), (4, 4, 4), "minecraft:oak_stairs", ridge="x")
    # door opening: carve air in the south wall
    BUILD.set(2, 1, 4, "minecraft:air")
    BUILD.set(2, 2, 4, "minecraft:air")
    # lantern inside, hanging from the ridge
    BUILD.set(2, 3, 2, "minecraft:lantern[hanging=true]")
```

Validate (fast loop — no rendering, no artifact):

```bash
mcbuild check hut.py
# hut.py — OK (97 blocks, 6 types, 0 errors, 0 warnings)
```

Render previews and export:

```bash
mcbuild run hut.py --out dist/ --preview
# run dir: dist/run-001
#   97 blocks, 6 types, dims 5x7x5 — 0 errors, 2 warnings
#   previews: 2 in previews/
#   trusted previews: 2 in previews_trusted/
#   faithful previews: 2 in previews_faithful/
#   artifact: hut.nbt (nbt, DataVersion 4903)
```

Each run gets an auto-versioned directory (`run-001`, `run-002`, …)
containing `report.json`, the three preview sets, and `hut.nbt`.
Iterate on what the previews show; re-run until the design is right.

For a full real-world example — shared `Geometry` factories, patterned
floors, canopy, per-variant palettes — see
[`examples/waystones/`](../examples/waystones/) (four 7×7×7 waystone
variants authored as ~50-line scripts over a common factory module).

## 5. Blockstate syntax and direction rules

Block strings are canonical `minecraft:name[prop=val,...]{nbt}`:

```python
"minecraft:oak_stairs[facing=north,half=bottom]"
"minecraft:chest{Items:[{Slot:0b,id:\"minecraft:stone\"}]}"
"minecraft:furnace[facing=east]{BurnTime:200s}"
```

Canonical form = name + properties **sorted alphabetically** + NBT
with top-level keys sorted. Property order never matters:
`[half=bottom,facing=north]` and `[facing=north,half=bottom]` are the
same palette entry. Malformed strings raise `ValueError` immediately
(empty name, unclosed brackets, duplicate keys, unbalanced NBT).

**Partial properties are legal — omitted props take vanilla defaults.**
`minecraft:oak_log[axis=y]` (no `waterlogged`) and
`minecraft:oak_leaves[persistent=true]` (no `distance`) both validate:
`mcbuild check` only verifies the properties you wrote, each against the
block's legal name/value list. mcbuilder never fills in the rest — the
`.nbt` palette entry carries exactly your properties, and Minecraft
resolves the missing ones to defaults when the structure is pasted. The
preview renderers assume the same defaults when matching models
(`facing=north`, `half=bottom`, `shape=straight`, `type=bottom`,
`axis=y`, `hanging=false`, `waterlogged=false`, `open=false`). Rule of
thumb: when the default is load-bearing for your build, write the
property explicitly.

**Direction convention: no silent inference.** `set`, `box`, `walls`,
`floor`, and `pillar` place your block string **verbatim** — no axis or
facing is ever guessed. Only helpers whose geometry implies a
direction compute one, and each documents its rule:

- `roof_gable(..., ridge="x"|"z")` — `ridge` is required, no default.
  Each row's `facing` points toward the eave it ascends from
  (downhill): `ridge="x"` ⇒ north-eave rows face `north`,
  south-eave rows face `south` (and `west`/`east` for `ridge="z"`).
  Passing a `facing` property yourself is a `BuildError` — the facing
  is computed, never merged. `half` defaults to `bottom`.
- `stairs_run` — step `i` at `(i·dx, i, i·dz)`, ascending *towards*
  `direction`. Each step gets `facing` = the **opposite** of the ascent
  direction and `half=bottom` — stairs face the climber (ascending
  north ⇒ facing south), matching vanilla placement. `width > 1`
  widens toward the positive perpendicular side.
- `railing(start, end, block)` — straight axis-aligned run (x or z
  constant, same y); anything else is a `BuildError`. Fence/wall
  connections resolve **in-game at paste time** — previews show
  unconnected posts.

Coordinate frame: **+X = east, +Y = up, +Z = south.** Direction words
are `north`/`south`/`east`/`west` (case-insensitive).

**Rotation.** `mcbuilder.rotation` implements the structure rotation
table used server-side by LostQoL's `StructurePaster`
(`rotate_position` / `rotate_blockstate` over `NONE`, `CLOCKWISE_90`,
`CLOCKWISE_180`, `COUNTERCLOCKWISE_90`): horizontal `facing` cycles
n→e→s→w per 90° clockwise, `axis` swaps x/z on 90° turns, sign/banner
`rotation` shifts +4/+8/+12 (mod 16); `half`, `shape`, `hinge` and
friends are invariant. A design verified here pastes correctly at all
four rotations.

## 6. Views

One grammar, semicolons only:

| Token | Meaning |
|---|---|
| `az<ddd>_el<dd>` | azimuth clockwise from north (−Z), elevation above horizontal — e.g. `az045_el025` |
| `orbit<n>_el<dd>` | n views from az000 stepping +360/n clockwise — e.g. `orbit8_el25` |
| `top` | straight down (elevation 90) |
| `iso` | pinned `az045_el035` |

A colon may follow `az`/`orbit`/`el` (`orbit:8_el:25`) — same thing.
Multiple views are semicolon-separated: `"az045_el025;top"`.

Precedence: **CLI `--views` / `--count` > script `views_config` >
default** (9 views: `orbit8_el25` + `top`). `--count N` appends an
N-view orbit at el25. Hard cap: **36 views** per render set.

```bash
mcbuild run hut.py --preview --views "iso;az000_el025;az180_el025;top"
```

See [docs/VIEWS.md](VIEWS.md) — the six standard views
(`az000/az090/az180/az270` at 25° elevation, `top`, `iso`) rendered
from a sample hut, with one-line descriptions.

## 7. The three preview tiers

`mcbuild run --preview` renders every resolved view in **three** tiers
into the run dir. Pick the tier for the question you're asking:

| Tier | Dir | What it is | When to use it |
|---|---|---|---|
| **fast** | `previews/` | textured cubes, quick | iteration speed, massing, palette read |
| **trusted** | `previews_trusted/` | simplified geometry, orientation-truthful, flat colors | verifying facing/axis/half before shipping an `.nbt` |
| **faithful** | `previews_faithful/` | real vanilla model geometry + real textures, Shadow Court presentation | player-facing verification, final sign-off |

**fast** renders textured cubes. It cannot show facing/axis state —
every entry is flagged `directions_untrusted` in `report.json`.
Never trust a direction from it. Blocks whose texture can't be
resolved render as flat fallback colors (with a warning).

**trusted** shows orientation truthfully: stairs as oriented
step shapes (facing × half), slabs as half-boxes, axis bands on
logs/pillars, posts for walls/fences, facing plates, rotation arrows
for signs/banners. No textures needed. Any directional block it
cannot render truthfully becomes a **labeled cube plus one warning
per block type** — check `report.json` warnings before the `.nbt`
goes anywhere near the plugin.

**faithful** resolves each blockstate through the vanilla client
assets (blockstate JSON → model JSON → textures) and projects the
**real model cuboids** — stairs get the true multi-box stair profile,
lanterns/chains/trapdoors their real shapes. Default output is the
presentation look: clean light background, soft contact shadow,
Minecraft per-face shading, no debug chrome. This is the verification
gate for anything player-facing — and the tier whose renders you
compare against reference screenshots.

Rule of thumb: iterate on **fast**, verify directions on **trusted**,
sign off on **faithful**.

## 8. CLI reference

```bash
mcbuild init [path] [--force]
# write a starter builder script (the §2 five-minute house) that passes
# `check` as-is. Default path: house.py in the cwd. Refuses to overwrite
# an existing file unless --force is given.
# Then: mcbuild check <path>  ->  mcbuild run <path> --preview

mcbuild check <script> [--config PATH]
# validate only. Prints "OK (N blocks, M types, E errors, W warnings)".
# Exit 1 on errors, 0 otherwise. No rendering, no artifact.

mcbuild run <script> [--out dist/] [--preview] [--views SPEC]
                     [--count N] [--config PATH] [--include-air]
# validate + export + previews into dist/run-NNN/.
# --preview renders all three tiers (skipped entirely on validation errors).
# --include-air writes air cells into the .nbt (default: air excluded).

mcbuild assets fetch --version <x.y.z> [--cache-dir DIR]
# one-time per version: registry + vanilla client assets (textures,
# block models, blockstates). Textures are always included — there is
# no separate textures step.

mcbuild diff run-001 run-002 [--out dist/] [--max 30]
# compare two runs' voxel data (read from each run's .nbt artifact).
# Prints added/removed/replaced cells, capped at --max entries.
# Exit 0 when identical, 1 when differences found. Writes a side-by-side
# preview comparison PNG (dist/diff-run-001-run-002.png) when both runs
# share a preview view.
```

### Iterating: tweak → run → diff

The intended loop: tweak the script, `mcbuild run`, then
`mcbuild diff <old> <new>` to see exactly what changed before trusting
the preview:

```bash
mcbuild run house.py --out dist/ --preview   # -> dist/run-004
mcbuild diff run-003 run-004
# diff run-003 -> run-004
#   12 changed cells: 9 added, 1 removed, 2 replaced (97 -> 105 cells)
#   + (3, 2, 1) minecraft:oak_planks
#   - (1, 0, 0) minecraft:stone
#   ~ (2, 1, 1) minecraft:oak_stairs[facing=north,half=bottom] -> minecraft:oak_stairs[facing=south,half=bottom]
#   ...
#   comparison: dist/diff-run-003-run-004.png
```

Run ids accept the bare number too (`mcbuild diff 3 4`). Both runs must
be clean — a run that failed validation exports no `.nbt`, and diff
says so instead of guessing.

Two things to know about what the diff compares:

- **Positions are bbox-relative.** The `.nbt` stores cell positions as
  offsets from each run's own bbox minimum, so the diff is anchored at
  each run's bbox origin — a build that moved wholesale reports as
  identical. If you added cells on the negative side and the origin
  shifted, treat the diff as "changed against the new origin".
- **The comparison image is a side-by-side, not a heatmap.** The PNG
  pairs the first preview view both runs share (each panel captioned
  with its run id, change counts in the title band). Changed cells
  aren't tinted on the renders — the exact cell list above is the
  source of truth; use the image to eyeball whether the change looks
  right in context.

### `report.json`

Written to every run dir:

| Field | Meaning |
|---|---|
| `errors[]` | validation failures: `block`, `message`, did-you-mean `suggestions`, `at: "script.py:line"` |
| `warnings[]` | allowlist hits, fallback textures, untrusted blocks, determinism hints |
| `block_counts` | post-crop, air excluded — your survival material shopping list |
| `dimensions` | post-crop bbox `{x, y, z}` |
| `views[]` | per PNG: `file`, `azimuth`, `elevation`, `label`, `directions_untrusted`, `directions_trusted` |
| `artifacts[]` | deploy artifacts: `file`, `format: "nbt"`, `data_version` |
| `overwritten_placements` | how many placements overwrote an earlier one (last-write-wins count) |
| `run_dir` | the run directory itself |

## 9. `.nbt` export → LostQoL pipeline

`mcbuild run` writes `<name>.nbt` next to `report.json`: a vanilla
structure-block file (gzipped NBT with `DataVersion`, `size`,
`palette`, `blocks` — the same shape a structure block saves).

- **DataVersion** comes from your pinned `mc_version` (client
  `version.json`'s `world_version`; 26.2 → 4903). Pin the version your
  server runs — a wrong DataVersion is a wrong `.nbt`.
- **Deterministic**: palette follows grid insertion order, blocks are
  sorted by (x, y, z), gzip uses `mtime=0` with no filename — the same
  grid always yields byte-identical output.
- **Air**: excluded by default (neither unset nor carved cells are
  written); `--include-air` writes them explicitly.
- **Entities/block entities**: out of scope — `entities` is written
  as an empty list. NBT on block strings is syntax-checked only.

**Deploy:** copy the `.nbt` into LostQoL's `resources/structures/`
(manual copy for now). `StructurePaster.placeAnimated()` pastes it
server-side, rotation-safe. The LostQoL UGC import feature lets
players import `.nbt` files themselves (plugin-side, separate scope).

### The `lostqol:waystone` contract

Custom namespaced blocks go on the `mcbuild.toml` **allowlist** and
pass through validation with a warning instead of an error — and
into the `.nbt` **verbatim**. From `examples/waystones/common.py`:

> The center block ``lostqol:waystone`` is a CUSTOM namespaced block. It is
> not part of vanilla Minecraft 26.2 — it exists only so the LostQoL
> plugin can replace/resolve it at .nbt import time (the plugin-side UGC
> import feature, separate scope).
>
> mcbuilder treats it as pass-through: the block is on this directory's
> ``mcbuild.toml`` allowlist, so validation emits one allowlist WARNING
> instead of an error, and the block string is written into the exported
> .nbt verbatim. mcbuilder never resolves, models, or previews it —
> ``mcbuild check`` flagging it as an allowlist warning is EXPECTED.

**The LostQoL plugin must replace/resolve it at `.nbt` import time.**
That is a plugin-side contract — mcbuilder's job ends at writing the
string through untouched.

## 10. Troubleshooting

**Stair rows show "gaps" / floating strips in the preview (faithful *and* trusted tiers).**
This is real Minecraft geometry, not a renderer bug. A stair block is
two boxes: a full-height half and a half-height half. When `roof_gable`
(or `stairs_run`) stacks rows 1 block up and 1 block over with the tall
half facing *away* from the next row, a 0.5-block see-through notch is
left between rows — vanilla Minecraft has the exact same notch, and
from a high isometric angle you can see through it to whatever is
below (background if the roof is floating). Both the trusted and
faithful tiers render it identically. If the gaps bother you: put
something under the roof (walls, a ceiling), or view from a lower
elevation where the rows overlap. Do **not** "fix" it by editing the
preview — the voxels are correct.

**`mcbuild: error: placements must be inside 'with BUILD:'`**
Every placement call (`set`, `box`, `place`, parts, …) must run inside
the `with BUILD:` block. Module-level code outside it can't place.

**`... does not define BUILD`** — the script must define a
module-level `BUILD = mb.Build(...)` instance.

**Validation error with "did you mean …?"** — the block name isn't in
the version-pinned registry. Take the suggestion, or check you pinned
the right `mc_version` (a 26.2 name won't validate against 1.21.4).

**`roof_gable computes 'facing' … pass the stair block without a facing
property`** — by design: the helper owns the facing. Same class of
error if you hand a `facing` to a part that computes it.

**`railing: run must be axis-aligned`** — start/end must share y and
have x or z constant.

**Allowlist warning for `lostqol:waystone`** — expected (see §9). Any
*other* allowlist warning means a non-vanilla block is flowing into
your `.nbt`: make sure that's intentional.

**`preview: 'minecraft:X' has no texture and rendered as a flat
fallback color`** — the fast tier couldn't resolve a texture (often
blocks whose texture comes via model indirection). The block still
exports fine; its *direction* in the fast preview is not trustworthy —
check the trusted/faithful tiers instead.

**`trusted preview: N `minecraft:X` rendered as labeled cube —
orientation not verified`** — the trusted tier can't render that
block's orientation truthfully. Treat those blocks as unverified
before shipping the `.nbt`.

**`too many views: N (max 36)`** — trim the view spec.

**Determinism warning (`imports 'random' — use BUILD.rng()`)** — raw
`random`/`numpy.random` breaks the same-seed-same-grid guarantee.
Use the seeded `BUILD.rng()`.

**My preview looks wrong.** Checklist, in order:
1. `mcbuild check` — 0 errors? (Errors block export *and* previews.)
2. Am I reading the right tier? (fast ≠ directions; see §7.)
3. `report.json` warnings — fallback textures / untrusted blocks?
4. Blockstate strings — did I hand-write a `facing` that fights the
   helper's computed one? (`roof_gable`/`stairs_run` own their facing.)
5. Still wrong? Compare the **faithful** tier against the trusted
   tier: if they disagree on an orientation, that's a renderer bug —
   report it with the script and the two PNGs.

## 11. FAQ

**Do I need the Minecraft client / a server to use this?**
No. `mcbuild assets fetch` downloads everything in one step: the block
registry plus the vanilla client assets — textures, block models, and
blockstates. Textures are fetched by default; there is no textures-only
mode and no separate textures step. The `.nbt` only touches a server
when LostQoL pastes it.

**Which Minecraft version?**
Whatever your server runs — pin it in `mcbuild.toml` (`mc_version`).
DataVersion, registry validation, and faithful-tier assets all follow
that pin. Lost SMP runs Paper 26.2 (DataVersion 4903).

**Can I use non-vanilla blocks?**
Yes via `allowlist` in `mcbuild.toml` — they pass validation with a
warning and are written into the `.nbt` verbatim (see §9). The plugin
must know what to do with them.

**How do rotations work?**
`mcbuilder.rotation` mirrors the server-side paster exactly
(§5). Design facing-north; pasting at 90°/180°/270° just works.

**Why do fences look unconnected in previews?**
Fence/wall connections are runtime state resolved by the game at
paste time, not stored blockstate data. The `.nbt` carries the bare
block; the server connects the arms.

**Why is my `.nbt` byte-identical across runs?**
Deterministic export (sorted blocks, normalized gzip) — intentional,
so content changes are diffable.

**Where do I put feedback / bugs?**
https://github.com/lzif/mcbuilder/issues
