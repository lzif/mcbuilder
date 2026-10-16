# mcbuilder Probe — API Friction Log (Floating Crystal Observatory)

Build script: `probe/crystal_observatory.py`
Final renders: `probe/renders/` (copied from `probe/dist/run-003/previews_faithful/`)
Runs: `probe/dist/run-001` → `run-002` → `run-003`

---

## 1. Missing Geometric Primitives (Curved, Conical, and Vector Shapes)

Building a floating crystal observatory immediately required four shapes that the DSL and `mb.part.*` catalog do not provide:
1. **Cylinder / hollow cylinder** (`observatory tower`, plinth, upper floor slab).
2. **Sphere / hemisphere / dome shell** (`telescope dome` with an open viewing slit).
3. **Cone / tapered frustum** (`floating island` craggy inverted cone + satellite islets).
4. **3D line / vector / tapered prism** (`angled crystal spires` and the `45° refracting telescope barrel`).

Currently `BUILD` and `mb.part` only offer rectilinear axis-aligned helpers (`box`, `walls`, `floor`, `carve`, `pillar`, `railing`, `stairs_run`, `roof_gable`). Any non-box archetype (towers, domes, arches, organic islands, diagonals) forces the agent back to raw nested `for x / for y / for z` math with `math.sqrt` and `BUILD.set`.
- **Diagonal voxelization trap**: In `run-001`, stepping along a 3D direction vector at integer steps (`for step in range(length)`) left diagonal-only connections at the tip (`end_rod` floating diagonally off the crystal tip). We had to hand-roll 0.5-block sub-stepping (`substeps = length * 2`) in `run-002` to ensure face-connected voxels. A built-in `line` / `beam` / `cone` helper would prevent agents from producing floating diagonal voxels.

---

## 2. Material Variation vs. Single-Block Helpers (Docs vs. API Mismatch)

`docs/GUIDE.md` §5 and `docs/build-patterns.md` §1 state as Technique #1:
> *"Material variation — never flat. Every surface gets noise. A single material over a large area reads as 'polosan' (plain) no matter the shape. Noise the base: ~30% secondary mottled variant mixed in."*

However, **every single helper in `BUILD` and `mb.part`** (`box`, `walls`, `floor`, `pillar`, `railing`, `stairs_run`, `roof_gable`) accepts only `block: str` (canonicalized once at the top of the helper).
- You cannot pass a weighted palette, list of blocks, or callable `fn(x, y, z)` to `BUILD.box`, `BUILD.walls`, `BUILD.floor`, or `BUILD.pillar`.
- Even `examples/waystones/common.py` had to write its own `floor_pattern(*, fn)` from scratch.
- To follow the guide's own #1 rule on the island, tower walls, and copper dome, we had to write a custom `mottled(choices)` helper and bypass `BUILD.box`/`BUILD.walls`/`BUILD.floor` in favor of manual loops calling `BUILD.set`.

---

## 3. `Geometry` Datablock Friction (`mb.Geometry` / `mb.part.*`)

While `Geometry` + `BUILD.place(geo, at=...)` works cleanly for simple translation stamping (we used it for `ISLET_GEO` and `rib_pillar`), composing or reusing `Geometry` hits immediate walls:
1. **No `.shift(dx, dy, dz)` / `.translate(...)` method on `Geometry`**:
   - Composing two geometries with `geo1 + geo2` requires them to already be at their target relative offsets, yet `mb.part.*` factories always anchor at `(0, 0, 0)`.
   - In `examples/waystones/common.py`, the author had to hand-roll `_shift(geo, dx, dy, dz)` by iterating `geo.cells()`.
2. **No `.rotate(...)` or `.mirror(...)` method on `Geometry`**:
   - `mcbuilder.rotation` already implements `rotate_position` and `rotate_blockstate` for `NONE`, `CLOCKWISE_90`, `CLOCKWISE_180`, `COUNTERCLOCKWISE_90`.
   - Yet `Geometry` does not expose `.rotate(...)`! To place overhanging cornice stairs (`deepslate_brick_stairs[facing=...,half=top]`), window frames, or radial buttresses around 4 sides of the tower, we could not define one `Geometry` and stamp it rotated 0°/90°/180°/270° — we had to manually write out the 4 cardinal directions and their facing strings.
3. **`Geometry` only has `.set(dx, dy, dz, block)` — no `.box()`, `.walls()`, or `.carve()`**:
   - Building a composite `Geometry` (like `make_floating_islet()`) means writing raw `.set()` loops because `Geometry` lacks the convenience methods that `BUILD` has.
   - There is also no way to `carve` (unset) a cell inside a `Geometry`.

---

## 4. Docstring Contradiction on `stairs_run` Facing

In `src/mcbuilder/part.py` (lines 185–190, 213–214) and `docs/GUIDE.md` §6:
- `stairs_run` sets `facing = dir_key` (ascending north ⇒ `facing=north`).
- However, `src/mcbuilder/parts.py` (lines 74–79) still contains the old, contradictory docstring:
  > *"each step's stairs block gets `facing` = the OPPOSITE of the ascent direction, and `half=bottom`. Stairs face the climber, so ascending north means facing south..."*
- Even though `parts.stairs_run` delegates directly to `part.stairs_run` (so it actually places `facing=north` when ascending north), reading `parts.py` gives the exact opposite rule.

---

## 5. Preview Tier Discrepancies & Fallbacks (`fast` vs `trusted` vs `faithful`)

1. **`minecraft:lightning_rod` is a magenta fallback cube in `previews_faithful` (and untextured in `previews`)**:
   - In `run-001`, we used `minecraft:lightning_rod[facing=south]` as part of the small spotting scope on the viewing deck. It passed `mcbuild check` with 0 errors/0 warnings, but during `mcbuild run --preview` it emitted:
     - `warning: preview: 'minecraft:lightning_rod' could not be textured and rendered as a flat fallback color`
     - `warning: faithful preview: 1 'minecraft:lightning_rod' rendered as magenta fallback cube — orientation not verified`
   - Oddly, `trusted` preview did NOT warn on `lightning_rod`, whereas `faithful` preview rendered a bright magenta cube on the deck. We replaced it in `run-002` with `cut_copper_slab` + `end_rod`.
2. **`minecraft:iron_chain[axis=y]` is a magenta fallback cube in `previews_trusted`, but works in `previews_faithful`**:
   - Both our build and `examples/waystones/waystone_classic_ruin.py` use `minecraft:iron_chain[axis=y]`.
   - `previews_faithful` renders chains with their true model, but `previews_trusted` does not recognize `iron_chain` in its axis-handler and drops a magenta cube with text label `iron_chain` + a warning in every run.
3. **`previews_trusted` color palette turns mottled surfaces into high-contrast camouflage**:
   - Because `previews_trusted` hashes/assigns vividly contrasting flat colors per block name (e.g., `stone` = red-orange, `moss_block` = royal blue, `stone_bricks` = lime green, `spruce_planks` = neon green), any build that uses mottled textures (per `docs/build-patterns.md`) becomes visually noisy in `previews_trusted`, making it hard to read the actual orientation wedges/bands.

---

## 6. `mcbuild diff` Iteration Loop Friction

We used `mcbuild diff run-001 run-002 --out probe/dist` during iteration and hit three sharp edges:
1. **Bbox-origin shift invalidates the entire voxel diff**:
   - Because `.nbt` stores coordinates relative to `(minx, miny, minz)`, moving the satellite floating islet by 2 blocks in X/Y/Z shifted the global bounding-box minimum.
   - As a result, `mcbuild diff run-001 run-002` reported **`3432 changed cells: 882 added, 873 removed, 1677 replaced (3081 -> 3090 cells)`** — flagging virtually every block in the build as changed even though 90% of the structure was untouched in world coordinates!
   - Storing the world-space origin offset in `report.json` (or anchoring diffs by world coordinates when available) would make `mcbuild diff` drastically more useful when exterior extremities change.
2. **Single global `BUILD.rng()` stream means early geometry edits Perturb downstream mottled blocks**:
   - Because all `mottled()` calls draw from one sequential `BUILD.rng()`, changing the loop bounds of the island at step 1 shifts the RNG state for the tower walls and dome at steps 3 and 5, causing hundreds of false-positive block replacements in `mcbuild diff`. A coordinate-hashed noise helper (e.g. `BUILD.noise_choice(x, y, z, palette)`) or per-section sub-RNG (`BUILD.rng("dome")`) would keep unrelated sections stable across edits.
3. **`mcbuild diff` comparison PNG uses `previews/` (`fast` tier) instead of `previews_faithful/`**:
   - `diff-run-001-run-002.png` pairs the `fast` tier renders (where stairs, slabs, clusters, and rods are blocky cubes or black fallback boxes) rather than `previews_faithful/`.
4. **Exit code 1 on non-empty diff**:
   - `mcbuild diff` exits with code `1` whenever differences exist (matching POSIX `diff(1)`), which causes shell one-liners or agent tool invocations to report a command failure.
