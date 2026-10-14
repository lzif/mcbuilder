# Plan (rev 2): Biome tint (`tintindex`) for the preview renderers — REVISED (2026-10-10, post fresh-context review)

**Branch (phase 2):** `acc/biome-tint` · **Base:** `main` @ `ab39e88` · **No code written, no files modified in this phase.**

## 1. Goal

Make the faithful tier (`preview_faithful.py`) and the fast tier (`preview.py`) apply vanilla biome tinting to faces whose model JSON declares `tintindex >= 0`, using **plains** as the single default biome. Tint is color-only; geometry, rotations, UV assignment, and the direction-trust guarantees are untouched.

## 2. Verified facts (read from the real 26.2 assets this session)

**Default biome — plains** (`data/minecraft/worldgen/biome/plains.json`, extracted from the 26.2 client jar, sha1-verified):
- `temperature: 0.8`, `downfall: 0.4`, `grass_color_modifier: None`, no fixed `grass_color`/`foliage_color` overrides.

**Colormap sampling formula** (vanilla `GrassColor`/`FoliageColor`/`DryFoliageColor` all delegate to a shared `ColorMapColorUtil.get` — confirmed via class-bytecode references in the 26.2 jar):
- `x = int((1 - t) * 255)`, `y = int((1 - t*h) * 255)` → plains = pixel **(50, 173)** on each 256×256 RGB colormap.
- Cross-checked: `grass.png` at (127,127) = `(124,189,107)` = `#7CBD6B`, exactly the wiki-documented inventory grass tint — the mapping is correct.

**Verified plains RGB values** (PIL reads from the 26.2 jar's colormaps):

| Source | Plains RGB | Hex |
|---|---|---|
| `grass.png` @ (50,173) | (145, 189, 89) | `#91BD59` |
| `foliage.png` @ (50,173) | (119, 171, 47) | `#77AB2F` |
| `dry_foliage.png` @ (50,173) | (163, 117, 70) | `#A37546` |
| water (vanilla default `0x3F76E4`, server-side) | (63, 118, 228) | `#3F76E4` |

- The grass/foliage/water values independently match the 26.2 biome-color table published by fmcmapper (a Fabric mod built for 26.2).
- **Discrepancy found and resolved:** fmcmapper's README claims plains dry-foliage `#7B4F19` — that pixel exists *nowhere* in the 26.2 `dry_foliage.png` (closest pixel anywhere is `(143,83,51)`; channel ranges are R 121–163, G 83–128, B 51–90). Since the shared `ColorMapColorUtil` applies the same formula, `#A37546` is correct for 26.2; the README value is stale. Phase 2 keeps a visual backstop (see §8).
- Fixed (non-biome) tints, confirmed via wiki Block/Item colors pages: birch leaves `#80A755` = (128,167,85), spruce leaves `#619961` = (97,153,97), lily pad `#208030` = (32,128,48).

**Which faces declare `tintindex`** (read from the 26.2 model JSONs):
- `grass_block.json`: `up` (`#top`) and the 4 overlay-element faces (`#overlay`) have `tintindex: 0`. Base `#side` faces do **not** — and must stay untinted: `grass_block_side.png` is the pre-tinted "fast graphics" texture (green strip baked in, sampled `(116,180,74)`), while `grass_block_side_overlay.png` is grayscale `(169,169,169)` + alpha, designed to be multiplied.
- `leaves.json` (parent of oak/jungle/acacia/dark_oak/mangrove/**birch/spruce/cherry/pale_oak**): all 6 faces `tintindex: 0`, texture `#all`.
- `tinted_cross.json` (short/tall grass, ferns, sugar cane, bush): `#cross`, `tintindex: 0`.
- `vine.json`: `#vine`, `tintindex: 0`.
- `tinted_flower_pot_cross.json` (parent of `potted_fern.json`): `#plant`, `tintindex: 0`.
- `flowerbed_1.json` (parent of `wildflowers_*` and `pink_petals_*`): the `#stem` side faces have **`tintindex: 1`** (verified directly — all 12 side faces); `#flowerbed` up/down faces have no tintindex. **Gating is `>= 0`, so tintindex 1 still tints** (see §7 test 8).
- `template_leaf_litter_*.json`: `up`/`down`, `#texture`, `tintindex: 0`.
- `lily_pad.json`: `#texture`, `tintindex: 0`.
- `bamboo_small_leaves.json` / `bamboo_large_leaves.json`: all 4 side faces `#texture`, `tintindex: 0`. The stalk models (`bamboo1_age0` etc.) have **no** tintindex on any face.

**Vanilla tint grouping** (which colormap each tinted block uses), from two independent 26.2-aligned implementations plus the wiki Color page:
- **Grass colormap:** grass block (top + overlay), short/tall grass, ferns, sugar cane, bushes, wildflowers/pink-petals stems, bamboo leaves, potted fern.
- **Foliage colormap:** oak, jungle, acacia, dark oak, mangrove leaves **+ vines**.
- **Dry-foliage colormap:** leaf litter.
- **Fixed:** birch, spruce, lily pad.
- **Explicitly untinted despite `tintindex: 0` in an inherited model** (vanilla registers no color provider → white tint): `cherry_leaves`, `pale_oak_leaves`, `stonecutter` saw faces, `bamboo` stalk parts (only the leaf models are tinted).

## 3. Design

**Single shared table + helper in `preview.py`** (the faithful tier already imports shared bits as `_fast` — follow that pattern; no new module):

```python
# Plains biome tints, sampled from the 26.2 client colormaps (see derivation
# comment: plains.json t=0.8/h=0.4 -> pixel (50,173) on each 256x256 map).
_PLAINS_GRASS        = (145, 189, 89)    # grass.png
_PLAINS_FOLIAGE      = (119, 171, 47)    # foliage.png
_PLAINS_DRY_FOLIAGE  = (163, 117, 70)    # dry_foliage.png
_PLAINS_WATER        = (63, 118, 228)    # vanilla default water color 0x3F76E4

_TINT_TABLE: dict[str, tuple[int, int, int]] = {
    # grass colormap
    "minecraft:grass_block": _PLAINS_GRASS,
    "minecraft:short_grass": _PLAINS_GRASS,
    "minecraft:tall_grass": _PLAINS_GRASS,
    "minecraft:fern": _PLAINS_GRASS,
    "minecraft:large_fern": _PLAINS_GRASS,
    "minecraft:potted_fern": _PLAINS_GRASS,
    "minecraft:sugar_cane": _PLAINS_GRASS,      # medium confidence, §9
    "minecraft:bush": _PLAINS_GRASS,            # medium confidence, §9
    "minecraft:wildflowers": _PLAINS_GRASS,     # medium-high, §9
    "minecraft:pink_petals": _PLAINS_GRASS,     # medium-high, §9
    "minecraft:bamboo": _PLAINS_GRASS,          # medium confidence, §9;
                                               # fast-tier limitation: §4.3
    # foliage colormap
    "minecraft:oak_leaves": _PLAINS_FOLIAGE,
    "minecraft:jungle_leaves": _PLAINS_FOLIAGE,
    "minecraft:acacia_leaves": _PLAINS_FOLIAGE,
    "minecraft:dark_oak_leaves": _PLAINS_FOLIAGE,
    "minecraft:mangrove_leaves": _PLAINS_FOLIAGE,
    "minecraft:vine": _PLAINS_FOLIAGE,          # medium-high, §9
    # dry-foliage colormap
    "minecraft:leaf_litter": _PLAINS_DRY_FOLIAGE,  # medium, §9
    # fixed tints
    "minecraft:birch_leaves": (128, 167, 85),   # #80A755
    "minecraft:spruce_leaves": (97, 153, 97),   # #619961
    "minecraft:lily_pad": (32, 128, 48),        # #208030
}
```

**Default-deny:** blocks not in the table get no tint even if their model declares `tintindex` (cherry/pale-oak leaves, stonecutter, etc.) — this exactly mirrors vanilla, where an unregistered block's tint is white.

```python
def _tint_image(img: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Multiply RGB channels by rgb/255; alpha untouched. Returns a NEW image."""
    # Mirror _shade_image's structure (split RGB, keep A).
```

**Algorithm (both tiers):** per-face, after UV crop + face-rotation, before directional shading:
`tinted = crop * (tint_r/255, tint_g/255, tint_b/255)` per channel, alpha preserved. Vanilla multiplies the tint into the vertex color before lighting; shading after tint matches that order.

## 4. Precise change locations

### `src/mcbuilder/preview.py` (fast tier + shared table)
1. **~line 340** (next to `_FLUID_FLAT`): add the plains constants, `_TINT_TABLE`, `_tint_image()`.
2. **`_FLUID_FLAT`** (line 340–346): `minecraft:water` `(52,120,235)` → `(63,118,228)` (verified plains water; no test asserts the old value — verified by grep).
3. **`_do_resolve`** (~line 213) → `_resolve_model_textures` (~line 199), arity 2→3:
   - `_do_resolve` additionally collects `tinted_vars: set[str]` — texture-variable names (post-`#` resolution, i.e. keys of the `images` dict) referenced by any face with `tintindex >= 0` in the resolved elements (first chain entry that has elements — the same model the faithful tier reads its elements from).
   - Every return point becomes a 3-tuple: the early `return {}, None` paths → `return {}, None, set()`; the final `return images, parent_leaf` (line 309) → `return images, parent_leaf, tinted_vars`.
   - `_resolve_model_textures` docstring → "Return (textures, parent_leaf, tinted_vars)."; its exception path → `return {}, None, set()`.
   - **Callers (M11):** line 550 `images, parent_leaf = ({}, None)` → `images, parent_leaf, tinted_vars = ({}, None, set())`; **line 552 `images, parent_leaf = _resolve_model_textures(name, props, assets_root)` → 3-unpack** (explicit).
   - Only internal callers exist (lines 208/552); tests don't touch these (verified by grep).
   - **Known fast-tier limitation — bamboo (M5, verified against real code):** `_do_resolve` resolves only the FIRST multipart apply's first model (`preview.py:233-240`: `apply[0]`, then `break`). In `bamboo.json` the multipart cases are ordered `age=0` → `age=1` → `leaves=small` → `leaves=large`, and the stalk cases use an `apply` **list** of 4 models — so resolution takes `bamboo1_age0`, whose faces carry NO tintindex (verified). The tinted leaf models (`bamboo_small_leaves`, `bamboo_large_leaves`, `tintindex: 0`) are never resolved in the fast tier, so `tinted_vars == set()` for bamboo there: **fast-tier bamboo renders stalk-only and never tints**. The faithful tier iterates every matching multipart case (`_model_applications`, `preview_faithful.py:356-360`) and tints the leaf faces correctly per-face — so `minecraft:bamboo` stays in the table and the faithful tier does the right thing.
   - **Design decision: document, don't fix.** Unioning `tinted_vars` across all applies would be unsound: texture var names are model-local. Correct multi-apply resolution in `_do_resolve` is a separate fast-tier fidelity feature, out of scope here.
4. **`_build_face_textures`** (~line 546): after the per-face `img` is chosen, in the **non-fallback branch only** (missing-texture flat colors stay untinted as a debug signal): `if var in tinted_vars and (tint := _TINT_TABLE.get(name)) is not None: img = _tint_image(img, tint)`. `name` is the full `minecraft:...` name from `_split_blockstate` — matches table keys.

### `src/mcbuilder/preview_faithful.py`
5. **`_resolve_block_quads`** face loop (~line 470–540): `block_name` is already in scope. After `crop = _face_uv_rotation_crop(crop, ...)` (~line 511) and **before** the uvlock/shade section, insert:
   `ti = face.get("tintindex", -1)`; `if has_real_texture and isinstance(ti,int) and ti >= 0 and (tint := _fast._TINT_TABLE.get(block_name)) is not None: crop = _fast._tint_image(crop, tint)`
   - `has_real_texture` = the `img is None` fallback branch (~line 495) was *not* taken — record with a flag; fallback flat colors stay untinted.
   - Tinting the per-face **crop** (a fresh `Image` from `.crop()`) is the cache-safety linchpin: `_load_texture_image`'s `tex_cache` (~line 177) holds source images shared across blocks/palette entries and is never mutated.
6. **`_FLUID_RGBA`** (line 581–588): water `(52,120,235,150)` → `(63,118,228,150)` — hue corrected to verified plains water, alpha 150 preserved (existing aesthetic).

**Not touched:** `_draw_textured_quad` (its RGBA path already combines quad mask with texture alpha — tinted RGBA flows through unchanged), `_shade_image`, all rotation/UV-ordering/uvlock code (~lines 380–470), `_face_base_corners`, `_order_corners_uv`, `resolve_block_quads`'s fluid/fallback dispatch, the asset pipeline (`assets.py` — no colormap extraction needed since values are hardcoded).

## 5. Cache-safety analysis
- **Faithful:** tint applies to the per-face crop, never to `tex_cache` entries. Two blocks sharing one texture file with different tints cannot cross-contaminate. The per-palette-entry `quad_cache` in `_render_view` is keyed by palette index = one block = one tint. ✓
- **Fast:** `_do_resolve` builds fresh PIL images per call (no persistent source-image cache); `tex_cache` in `_render_view` is per palette index. `_tint_image` returns a new image and never mutates its input (defensive; mirrors `_shade_image`). ✓

## 6. Direction-trust guarantees — untouched
Tint is applied to pixel values only, after UV crop/rotation and before shading. No change to: element/model rotations, `_rot_y`/`_rot_x` orientation model, painted-on UV corner assignment, uvlock v-pinning, face culling, quad depth sorting, or the affine warp in `_draw_textured_quad`. The #4 stair-facing fix and all direction-parity tests are unaffected by construction.

## 7. Regression test plan (new `tests/test_biome_tint.py`)

**Fixture fix (M9):** the `assets_root`/`tex_cache` fixtures live in `tests/test_preview_faithful.py:122-128` — `tests/conftest.py` today only adjusts `sys.path` (verified: 8 lines, no fixtures). A new test file cannot import fixtures from another test module. So phase 2 first moves `assets_root` + `tex_cache` **and the helpers they depend on** (`_write_json`, `_write_tex`, `make_assets`) into `tests/conftest.py`. `test_preview_faithful.py` keeps using them unchanged (pytest resolves from conftest); run the suite after the move to prove no behavior change.

**Hermeticity:** no test may depend on the real `~/.cache/mcbuilder/26.2` client cache (the existing 390 tests are fully hermetic; `test_assets.py` mocks the network). Extend `make_assets` (now in conftest) with tint-specific fake models, all with solid-color textures so pixel assertions are exact:

- `test_tint_cube`: parent `minecraft:block/cube_all`, textures `{"all": "test:block/tint_gray"}` (solid (200,200,200)), full-cube element, all faces `{"texture": "#all", "tintindex": 0}`. Blockstate `{"variants": {"": {"model": "test:block/test_tint_cube"}}}` (`_match_variant` accepts the `""` key — verified).
- `test_tint_index1`: same shape, all faces `tintindex: 1` (wildflowers/flowerbed analog).
- `test_tint_overlay`: grass-block analog — element 0: north `#side` (solid (210,210,210)), no tintindex; element 1: north `#overlay` (solid (160,160,160)), `tintindex: 0`. Produces two world-north quads.
- `test_tint_multi`: multipart bamboo analog — blockstate `{"multipart": [{"apply": {"model": "test:block/test_stalk"}}, {"apply": {"model": "test:block/test_leaf"}}]}`; `test_stalk`: full cube, no tintindex, `#all`; `test_leaf`: cross element, faces `#texture` with `tintindex: 0`.
- `test_tint_cherry`: child of a parent declaring `tintindex: 0` on all faces (cherry-leaves analog), but the block itself gets no table entry.

Table entries for `test:`-namespace blocks are injected via `monkeypatch.setitem(_fast._TINT_TABLE, ...)` (auto-restores; never permanently mutates the real table). Both tiers read `_TINT_TABLE` at call time, so the monkeypatch is visible to both.

Test list:
1. **Pinned values:** `_TINT_TABLE["minecraft:grass_block"] == (145,189,89)`, foliage/dry/water/fixed entries — guards the verified numbers against drift.
2. **Faithful overlay disambiguation (L5):** `resolve_block_quads("test:test_tint_overlay", assets_root, {})` returns quads as `(ordered, world_n, img)` 3-tuples (`_FACE_NORMALS["north"] == (0,0,-1)`). North quads = `[q for q in quads if q[1] == (0,0,-1)]` → assert exactly **2**; one image mean ≈ tinted overlay (`(160,160,160)` × tint `(100,150,200)` → ≈ (63,94,126), tolerance ±3), the other mean ≈ raw side `(210,210,210)` ±1. Mirrors the real grass block without depending on the 26.2 cache.
3. **Faithful leaves analog:** `test_tint_cube` (monkeypatched tint) → all 6 face quads tinted; **fixed-tint analog:** two blocks sharing one texture file with different monkeypatched table colors → their quad means differ (pins per-*block* table lookup, not per-texture).
4. **Untinted controls:** `test:test_stone`-analog (no table entry) and `test_tint_cherry` (inherited `tintindex: 0`, no table entry) → quad means pixel-identical to raw textures (default-deny, mirroring real cherry/pale-oak leaves).
5. **Cache isolation:** resolve two tinted blocks sharing one `tex_cache`; assert the cached source images are byte-identical to the raw PNGs and the two blocks' quad textures differ.
6. **Fast tier:** `_build_face_textures("test:test_tint_cube", ...)` (monkeypatched tint) → `["up"]` mean ≈ tinted, and a face whose var is not in `tinted_vars` stays raw; `_fallback_color("minecraft:water") == (63,118,228)`.
7. **Water:** faithful water top-face pixel == `(63,118,228,150)` (shade 1.0; fluid path needs no assets).
8. **NEW — wildflowers gating regression (M4):** `test_tint_index1` (faces with `tintindex: 1`, monkeypatched table) → faces tinted. Pins the `>= 0` gating behavior, not `== 0` — the real `flowerbed_1.json` `#stem` faces declare `tintindex: 1` (verified).
9. **NEW — fast-tier bamboo limitation (M5):** `test_tint_multi` (first apply untinted, second apply tinted — same ordering shape as real `bamboo.json`) with a monkeypatched table entry: `_resolve_model_textures(...)` returns a 3-tuple whose third element `== set()`; `_build_face_textures` faces are untinted. Pins the documented §4.3 limitation: fast tier resolves only the first multipart apply.
10. **Full suite:** `cd ~/workspace/mcbuilder && .venv/bin/python -m pytest tests/ -q` — 390 existing tests must stay green.

## 8. Risks / open questions
1. **Medium-confidence table entries** (`sugar_cane`, `bush`, `bamboo`, `vine`, `wildflowers`, `pink_petals`, `potted_fern`, `leaf_litter`): assigned from 26.2-aligned third-party BlockColors tables + model/texture evidence, not from decompiled Mojang code. Mitigation: each is a one-line table change; phase 2 renders each beside an in-game plains screenshot and drops/corrects mismatches. The high-value entries (grass block, 5 leaves, birch/spruce, lily pad, water) are high-confidence.
2. **Dry-foliage `#A37546` vs fmcmapper's `#7B4F19`:** resolved in favor of the 26.2 file + shared-`ColorMapColorUtil` bytecode evidence, but phase 2 should eyeball leaf litter against in-game plains.
3. **Redstone dust / melon-pumpkin stems** declare `tintindex` but use power/age-based tints, not biome tints — explicitly out of scope; they stay untinted (known limitation, document in code comment).
4. **Cauldron water** (`template_cauldron_*` has `tintindex`) — cauldrons are block entities with no rendered model in mcbuilder (magenta fallback today); out of scope.
5. **Fast-tier bamboo: stalk-only, never tinted (§4.3, M5).** Known and documented; the faithful tier tints the leaf faces correctly. Unioning tinted vars across multipart applies was rejected as unsound (texture var names are model-local).
6. **Performance:** tint is a ≤16×16 per-face multiply for table blocks only; `_do_resolve` gains one small element walk per palette entry (cached per render). Negligible.
7. **Version drift:** values are 26.2-verified and pinned by test; a comment records the derivation (plains.json t=0.8/h=0.4 → pixel (50,173)). A future per-biome feature would add `textures/colormap/` to `_CLIENT_PREFIXES` in `assets.py` — deliberately not done here.
8. **Water alpha** stays 150 (existing look); only hue corrected.

## 9. Out of scope (and why)
- Per-biome selection / biome-blend: needs colormap extraction + climate data plumbing — a separate feature; plains default covers the renderer's needs today.
- `cherry_leaves`, `pale_oak_leaves`, `stonecutter`, `azalea_leaves`, `pale_hanging_moss`, `mangrove_propagule`: vanilla applies no tint (no color provider / no tintindex) — covered by default-deny, no code needed.
- Redstone/stem tint functions (non-biome math).
- Any asset-pipeline change.

## 10. Suggested phase-2 work order
0. `tests/conftest.py`: move `assets_root`/`tex_cache` fixtures + `_write_json`/`_write_tex`/`make_assets` helpers (M9); run `pytest` to confirm no behavior change. Extend `make_assets` with the §7 tint fake models.
1. `preview.py`: constants + table + `_tint_image` + water color.
2. `preview.py`: `tinted_vars` in `_do_resolve` / `_resolve_model_textures` / `_build_face_textures` (explicit 3-unpacks at lines 550/552, M11) + bamboo-limitation code comment.
3. `preview_faithful.py`: face-loop tint + water color.
4. `tests/test_biome_tint.py` (§7).
5. Full `pytest` (390 green) + visual spot-check renders (grass block, oak vs birch leaves, vine, leaf litter, water) against in-game plains references; adjust medium-confidence entries if needed.
6. Commit on `acc/biome-tint` with no AI/tool attribution (per standing rule).

**Deliverable of this phase:** this plan document. No code written, no files modified, nothing committed.

---

### Reviewer-item disposition

- **M4 (flowerbed tintindex 1):** verified in the 26.2 cache — `flowerbed_1.json` side `#stem` faces all declare `tintindex: 1`; up/down `#flowerbed` faces have none. §2 row corrected; gating stays `>= 0`; new test 8 pins it with a `tintindex: 1` fake model.
- **M5 (fast-tier bamboo):** verified the exact code path — `_do_resolve` takes the first multipart apply's first model (`preview.py:233-240`), and `bamboo.json` orders stalk cases before leaf cases; `bamboo1_age0` has no tintindex, `bamboo_small_leaves` has `tintindex: 0`. Chose **document-as-limitation** over unioning: unioning is unsound because var names are model-local. Faithful tier iterates all cases and tints correctly; bamboo stays in the table; new test 9 pins `tinted_vars == set()` for the fast tier.
- **M9 (fixtures):** verified `conftest.py` is 8 lines of `sys.path` only; fixtures at `test_preview_faithful.py:122-128`. Phase-2 step 0 moves them (plus helpers) into conftest.
- **M11 (3-unpack):** spelled out explicitly — lines 550/552 in `_build_face_textures`, plus every `_do_resolve` return point and the wrapper exception path.
- **L5 (grass two-north-quads):** verified `grass_block.json` has two elements (base `#side` untinted north + overlay `#overlay` tinted north). Test 2 uses a hermetic fake analog and asserts exactly 2 north quads with one tinted + one untinted.
