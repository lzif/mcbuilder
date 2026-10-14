# Plan (rev 2): Smooth Lighting / Ambient Occlusion for the Faithful Preview Tier — REVISED (2026-10-10, post fresh-context review)

**Scope:** `src/mcbuilder/preview_faithful.py` only (the faithful tier). No changes to `preview.py` (fast tier), `preview_trusted.py`, geometry, or orientation logic. **Direction-trust guarantees are untouched** — this is lighting-only: no vertex positions, normals, UV assignment, sort keys, or culling rules change.

**Phase:** PHASE 1 — plan only. No code, no file modifications, no commits. Implementation later on branch `acc/smooth-lighting`.

**Revision note:** rev 2 addresses a fresh-context review of rev 1 against `preview_faithful.py` at git `ab39e88` (945 lines). Seven findings fixed: H1 (quad tuple has no normal — rev 1's core insertion point was a misread), M1 (entity-approximation-aware classifier), M2 (ice/slime/honey), M3 (None textures), M7 (false "verified by grep" claim), M10 (signature inconsistency), L1 (drifted line numbers). All line references below are re-verified against `ab39e88`.

**Recommended merge position: LAST** — after fluid-height → biome-tint → block-entities. The classifier (§2.1) is written to be merge-order-independent via an explicit `hasattr` guard on the entity path.

## 1. What exists today (verified by reading the code at ab39e88)

- **Quad pipeline** (`_resolve_block_quads`, line 466): resolves blockstate → model JSON → element cuboids → per-face quads `(points, normal, texture_image)`. `points` are 4 block-local coords in UV order `[(u0,v0),(u0,v1),(u1,v1),(u1,v0)]`; `normal` is axis-snapped world-space. Face shading is **baked into the cached texture** via `_shade_image(crop, _SHADES[world_n])` (line 443) with the classic vanilla constants `_SHADES` (line 103: up 1.0, down 0.5, N/S 0.8, E/W 0.6).
- **Culling** (`_render_view`, line 761): back-face culling only (`sum(n*d) >= -1e-9` skip, line ~828). **There is no hidden-face/occlusion culling anywhere** — no `_renderable_mask` equivalent for faces, and **no opacity classification exists** in the codebase. Interior faces of adjacent cubes are simply overdrawn by the painter's algorithm.
- **Depth sort** (line 836): `quads.sort(key=lambda t: (-t[0], t[1], t[2], t[3], t[4]))` — deterministic painter's order.
- **Quad tuple (CORRECTED from rev 1):** the collect loop appends at **line 833** a 9-tuple `(depth, x, y, z, seq, wpts, tex, _is_fallback, block)` — **no normal**. The draw loop at **line 839** unpacks exactly those 9. `normal` exists only inside the collect loop (`for pts, normal, tex in block_quads:` at ~line 827) and is dropped. The comment at line 808 is stale and wrong on both shape and names. Verified: the only append to `_render_view`'s local `quads` is :833, the only unpack is :839.
- **`_draw_textured_quad`** (line 634): affine warp (numpy, `lstsq`-fit texture→screen), polygon mask, paste; RGBA path combines quad mask × texture alpha. Signature `(canvas, pts_uv, tex)`; called from `_render_view` (line 847) **and directly from tests** (`tests/test_preview_faithful.py:405` and `:470` — rev 1's "no other callers" claim was false).
- **Render-time grid data** (`render`, line 873): `arr` = int32 dense array `[x,y,z]` in array coords, `palette` = canonical blockstate strings, `-1` = UNSET, `"minecraft:air"` at its interned index (found via `palette.index`, never assumed 0). `_render_view` already converts cell → array coords (`x = lx + x0`, ~line 825).

## 2. Design

### 2.1 Opacity classification (new; nothing to reuse)

New function `_block_occludes_ao(canonical, assets_root, tex_cache) -> bool`, computed **once per `render()` call per palette entry**, producing a bool array `occ_idx` aligned with the palette, then expanded to a padded cell grid `occ` (shape `arr.shape + 2`, out-of-bounds = air = non-occluding).

The classifier **mirrors `resolve_block_quads`' (line 610) dispatch order exactly**, so classification always matches what is actually rendered, in any merge order:
1. UNSET (`-1`) / `"minecraft:air"` → `False`.
2. `_FLUID_RGBA` (line 581): water/lava → `False`; `minecraft:chest` (solid wooden-box stand-in) → `True`.
3. `assets_root is None` → `True` (fallback magenta cube).
4. **Entity path** (block-entities gap): guarded by `hasattr(module, "_try_entity_quads")` — pre-gap4 the attribute doesn't exist and this step is skipped entirely (banners/chests fall through to the model/fallback path, matching the pre-gap4 render). When present, call `_try_entity_quads(name, props, root, tex_cache)` (props from `_fast._split_blockstate(canonical)`, shared `tex_cache`):
   - returns `None` → fall through (entity texture missing → the render degrades identically: chest → wooden box via `_FLUID_RGBA`, trapped/ender/copper chests and banners → magenta cube).
   - returns quads → kind-based: **banner-kind** (`name.endswith("_banner")`, covers `<color>_banner` and `<color>_wall_banner`) → `False` (thin cloth + pole + crossbar; nothing fills the cube); **chest-family** (the other 11 entity names) → `True` (near-full compound box, approximately right).
5. **Explicit non-occluding set** (checked BEFORE the texture heuristic): `{minecraft:ice, minecraft:slime_block, minecraft:honey_block}` → `False`. Translucent in vanilla, don't occlude AO. Verified via 26.2 assets (uniform alpha 180–191 → RGBA through `_load_texture_image`); the explicit set is load-bearing for the None-texture case (rule 6's None→opaque would otherwise misclassify an ice block whose texture failed to load) and documents vanilla semantics. One-line extensible.
6. **Model path:** `True` **iff** (a) the union of the resolved elements' `from`/`to` boxes covers the full `[0,0,0]–[16,16,16]` cube (reuse `_model_applications` at line 333 + `_resolve_model_elements_and_textures` at line 245; use raw unrotated boxes), **and** (b) every resolved face texture is opaque — i.e. `img is None` (missing → the renderer degrades that face to an **opaque** flat RGB color, line ~525, so opaque is the render-consistent classification) **or** `img.mode != "RGBA"` (recall `_load_texture_image`, line 211, already demotes fully-opaque RGBA to RGB, so `RGBA` ⟺ genuinely transparent pixels). This makes **glass / stained glass non-occluding automatically**, matching vanilla.
   - **Explicit exception: leaves occlude** (`name.endswith("leaves")` → `True` even with transparent texture). Vanilla treats leaves as opaque cubes for AO. Flagged as verify-against-vanilla.
7. Model resolution fails (`_model_applications` empty or elements None) → fallback magenta cube → `True`.
- **Partial blocks** (stairs, slabs, walls, fences, lanterns, trapdoors, …) are non-occluding at cell level — they fail the full-cube test. Documented v0 simplification vs vanilla (which samples sub-cell shapes); partial blocks don't *cast* AO onto neighbors but still *receive* it.

### 2.2 Vertex AO sampling rule

New pure function `_vertex_ao_level(v_local, normal, cell, occ_padded) -> int` (0–3). **Canonical signature** — used identically everywhere.

The draw loop gains the face normal by **extending the quad tuple**: collect loop (line 833) appends `(depth, x, y, z, seq, wpts, normal, tex, _is_fallback, block)` (10 items); sort key at line 836 (`-t[0], t[1], t[2], t[3], t[4]`) unaffected (indices 0–4 unchanged); draw loop (line 839) unpacks `for _, x, y, z, _, wpts, normal, tex, is_fb, block in quads:`; stale comment at line 808 fixed.

Sampling rule (per quad vertex):
- `v_local` = vertex minus cell, in [0,1] (fractional allowed for partial-block quads).
- Let `a` = normal axis; `t1, t2` = the two tangent axes (fixed order `(0,1,2) minus a` → deterministic).
- For tangent axis `t` with local coord `vt`:
  - `vt <= 1e-9` → neighbor offset `ot = -1`
  - `vt >= 1 - 1e-9` → `ot = +1`
  - else (interior vertex, e.g. stair tread at 0.5) → `ot = 0` — sample the cell directly outside the vertex.
- Sample the three cells in the face-adjacent layer (padded `occ` grid, `+1` shift): `side1` (normal step + ot1·e_t1), `side2` (normal step + ot2·e_t2), `corner` (normal step + both).
- **Vanilla rule:** `level = 0 if (side1 and side2) else 3 - (side1 + side2 + corner)` with bools as ints.
- Sanity: open face → 3; one side → 2; one side + corner → 1; two sides → 0.

Vectorization: per quad, build the 4×3 offset triples with plain Python arithmetic, then **three fancy-index reads** on the padded bool array.

### 2.3 Brightness curve

`_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)` for levels (0,1,2,3).
- **0.4 floor** corroborated by thelinuxseal/nanocraft commit (2026-09-26) "fix ambient occlusion treating air as solid".
- **Linear 0.2 steps**: standard reconstruction of vanilla's per-level ramp. **Clearly labeled as a vanilla-derived approximation, not byte-verified from decompiled vanilla** — single tunable constant.
- **Composition with `_SHADES`: MULTIPLY, don't replace.** `_SHADES` stays baked into the cached texture (palette-level, view-independent); AO multiplies per-pixel at draw time: `final = texel × shade_face × ao_vertex`.

### 2.4 How AO flows into `_draw_textured_quad` (line 634)

- Signature becomes `_draw_textured_quad(canvas, pts_uv, tex, ao=None)` — `ao` = 4 brightness factors in `pts_uv` order (matches `wpts` order 1:1 in the draw loop). Default `None` = all-1.0 → **byte-identical to current behavior** (direct unit tests calling it with 3 positional args keep passing).
- Draw loop: compute 4 factors per quad; if all exactly `1.0` (`_AO_BRIGHTNESS[3]` is exactly `1.0`), pass `ao=None` (**fast path**: skips brightness pass, zero float error, isolated-block renders pixel-identical).
- When `ao` given: after the existing warp, fit a **single affine** brightness function from the 4 `(sx,sy) → ao` correspondences via `lstsq`, evaluate over the bbox with existing `_ox/_oy` grids, `clip(0,1)`, multiply into warped RGB — **RGB only on the RGBA path** (alpha is transparency, same reasoning as `_shade_image`'s RGB-only shading). `.astype(np.uint8)` truncation matches `_shade_image`'s `int(v*factor)` semantics.
- Affine is exact here: every quad is an affine image of a planar rect (blockstate/element rotations are affine), so screen quads are parallelograms where affine ≡ bilinear. `lstsq` on 4 parallelogram corners is exact.
- **Deliberate non-goal**: vanilla's quad-diagonal flip (anisotropy fix) — unnecessary with whole-quad affine interpolation. Revisit only if artifacts appear.

### 2.5 Precise change locations (`src/mcbuilder/preview_faithful.py`, git `ab39e88`)

| # | Location | Change |
|---|----------|--------|
| 1 | After `_SHADES` (line 103) | Add `_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)` + comment (approximation status, nanocraft floor evidence) |
| 2 | New section after `_resolve_model_elements_and_textures` (line 245) | `_block_occludes_ao(canonical, assets_root, tex_cache) -> bool` — dispatch-mirroring classifier per §2.1 |
| 3 | New section near #2 | `_vertex_ao_level(v_local, normal, cell, occ_padded) -> int` (pure sampler, §2.2) |
| 4 | `_draw_textured_quad` (line 634) | Add `ao=None` param; brightness-mask array alongside polygon mask; RGB-only multiply |
| 5 | `_render_view` signature (line 761) + collect (lines 808–833) | New `occ_padded` param; extend tuple at :833 to 10 items; fix stale comment at :808; sort key at :836 untouched |
| 6 | `_render_view` draw loop (lines 839–847) | Unpack 10-tuple; compute 4 AO factors per quad; pass to `_draw_textured_quad` at :847; fast path when all 1.0 |
| 7 | `render()` (line 873) | Compute palette-aligned `occ_idx` once (reuses `tex_cache`), build padded `occ` grid over `arr`, pass into `_render_view` |

`resolve_block_quads` (line 610) return contract `(quads, is_fallback)` **unchanged** — AO is cell/neighbor-dependent, cannot live in the palette-level quad cache. `render()`'s `RenderResult`/`info` shape unchanged.

## 3. Performance estimate & mitigations

- **Opacity grid**: O(palette entries) model resolutions, once per `render()` — reuses `tex_cache`; negligible.
- **Sampling**: 3 vectorized fancy-index reads per quad on padded bool array — ~µs per quad; 10k quads ≈ tens of ms.
- **Brightness mask**: only for quads with *any* darkening (fast path skips the rest): one 4-point `lstsq` (~10µs) + vectorized multiply-add — roughly +30–60% of existing warp cost for affected quads only.
- **Mitigations**: (1) palette-level opacity precompute, (2) padded-array vectorized sampling, (3) all-1.0 fast path, (4) no per-view recomputation.
- **Determinism**: pure functions of `(arr, palette, quads)`; fixed tangent-axis order; `lstsq` bit-deterministic on identical inputs; no randomness, no dict-order dependence (name sets for membership only); sort keys untouched.

## 4. Regression test plan (new tests in `tests/test_preview_faithful.py`)

Sensitive existing tests: `test_stair_row_notches_are_real_geometry` (stairs partial → non-occluding → zero AO change; bg-fraction assertion unaffected) and `test_lantern_crossbars_no_black_smear` (isolated → all-AO-3 → fast path → pixel-identical). Phase 2 must re-check both explicitly.

New tests:
1. **`test_ao_open_face_uniform`**: isolated stone cube → top-face pixels identical RGB; `_draw_textured_quad(..., ao=None)` vs `ao=(1,1,1,1)` → identical canvas.
2. **`test_ao_inner_corner_darkens`**: floor + wall inside corner; mean brightness at inner corner patch **strictly less** than outer-edge patch of same face.
3. **`test_ao_level_sampler_unit`**: all-air → 3; one side → 2; side+corner → 1; both sides → 0; interior-vertex (`vt=0.5`) → samples cell directly outside.
4. **`test_ao_occlusion_classification`** (extended): full opaque cube → True; glass-like (RGBA) → False; slab/stairs (partial) → False; `*leaves` (RGBA) → True; water/lava → False; air → False; **ice/slime_block/honey_block → False**; **missing texture (None) → True, no exception**.
5. **`test_ao_tinted_leaves_composition`** (NEW): oak leaves tinted (post-gap1) AND occluding. Unit-level: `_draw_textured_quad` with pre-tinted RGBA texture + `ao=(0.4,0.4,0.4,0.4)` → pixels equal tint × 0.4 (alpha untouched). Render-level (if gap1 landed): leaves adjacent to stone wall → inner-corner leaf pixels strictly darker than open-face leaf pixels of same tint.
6. **`test_ao_entity_classification`** (NEW): `hasattr`-guarded — if `_try_entity_quads` exists: `trapped_chest` → True, `white_banner` → False; else both → True (pre-gap4 they render as magenta fallback cube; classification must match the render).
7. **`test_ao_deterministic`**: render mixed grid twice → identical PNG bytes (md5).
8. **`test_ao_perf_smoke`**: synthetic 12×12×12 mixed stone/air grid via `FakeGrid` within a bound calibrated in phase 2 against pre-AO baseline (e.g. < 2× baseline; measure on this VM, don't guess).

## 5. Risks / open questions

1. **Brightness curve is an approximation** (0.4 floor corroborated, linear ramp assumed). Phase-2 validation: place a 2×2×2 stone corner on Nile and eyeball against a vanilla client with smooth lighting on (manual).
2. **Partial blocks don't cast AO** (cell-level sampling can't see sub-cell shapes) — documented v0 gap; shape-aware sampling is future work.
3. **Leaves-occlude** follows vanilla but contradicts the transparent-texture heuristic — explicit exception; one-line change if wrong in practice.
4. **Painter's-order interplay**: AO computed per quad independently of draw order — sort order can't corrupt it. Fluids receive AO (slight deviation from vanilla which skips AO on fluids) — visually coherent; flagged, not blocked.
5. **Anisotropy**: skipped; revisit if corner gradients look twisted.
6. **`test_stair_row_notches_are_real_geometry`** parity holds (AO not ported to trusted tier; stairs cast nothing); re-run to confirm.
7. **Tinted glass**: RGBA → heuristic says non-occluding, but vanilla blocks light through tinted glass (unverified). Left to heuristic for v0; include a tinted-glass corner in the phase-2 in-game eyeball check and flip to explicit `True` if vanilla disagrees.

## 6. Confirmation

- **Direction-trust guarantees untouched**: no changes to vertex positions, normals, UV corner assignment/painting, `_order_corners_uv`, rotation helpers, variant/multipart selection, culling, or sort keys. Purely photometric, applied after geometry is final. (The tuple extension carries the existing `normal` through — it does not create or alter any normal.)
- **390 existing tests must stay green**: no existing function signatures break (`ao` optional; `resolve_block_quads`/`render` contracts unchanged; `_render_view` internal — new `occ_padded` param has no external callers); all-1.0 fast path keeps isolated-block renders pixel-identical; phase 2 runs the full suite on branch `acc/smooth-lighting`.
- **No AI/tool attribution** in any git-facing artifact.
