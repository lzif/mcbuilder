# Plan: Smooth Lighting / Ambient Occlusion for the Faithful Preview Tier

**Scope:** `src/mcbuilder/preview_faithful.py` only (the faithful tier). No changes to `preview.py` (fast tier), `preview_trusted.py`, geometry, or orientation logic. **Direction-trust guarantees are untouched** — this is lighting-only: no vertex positions, normals, UV assignment, sort keys, or culling rules change.

## 1. What exists today (verified by reading the code)

- **Quad pipeline** (`_resolve_block_quads`, line 466): resolves blockstate → model JSON → element cuboids → per-face quads `(points, normal, texture_image)`. `points` are 4 block-local coords in UV order `[(u0,v0),(u0,v1),(u1,v1),(u1,v0)]`; `normal` is axis-snapped world-space. Face shading is **baked into the cached texture** via `_shade_image(crop, _SHADES[world_n])` (line 443) with the classic vanilla constants `_SHADES` (line 103: up 1.0, down 0.5, N/S 0.8, E/W 0.6).
- **Culling** (`_render_view`, line 761): back-face culling only (`sum(n*d) >= -1e-9` skip). **There is no hidden-face/occlusion culling anywhere** — no `_renderable_mask` equivalent for faces, and **no opacity classification exists** in the codebase (grep for `occlud`/`opaque`/`neighbor` found nothing render-related). Interior faces of adjacent cubes are simply overdrawn by the painter's algorithm.
- **Depth sort** (line ~790): `quads.sort(key=(-depth, x, y, z, seq))` — deterministic painter's order.
- **`_draw_textured_quad`** (line 634): affine warp (numpy, `lstsq`-fit texture→screen), polygon mask, paste; RGBA path combines quad mask × texture alpha. Signature `(canvas, pts_uv, tex)`; only called from `_render_view` (line ~803). No other callers in `src/` or `tests/` (verified by grep).
- **Render-time grid data** (`render`, line 873): `arr` = int32 dense array `[x,y,z]` in array coords, `palette` = canonical blockstate strings, `-1` = UNSET (never placed), `"minecraft:air"` at its interned index (found via `palette.index`, never assumed 0). `_render_view` already converts cell → array coords (`x = lx + x0`).

## 2. Design

### 2.1 Opacity classification (new; nothing to reuse)

Since no occlusion classification exists, add one — **data-driven, no hardcoded block denylist**:

- New function `_block_occludes_ao(canonical, assets_root, tex_cache) -> bool`, computed **once per `render()` call per palette entry** (not per cell, not per view), producing a bool array `occ_idx` aligned with the palette, then expanded to a padded cell grid `occ` (shape `arr.shape + 2`, out-of-bounds = air = non-occluding):
  - UNSET (`-1`) / `"minecraft:air"` → `False`.
  - `_FLUID_RGBA` (line 581): water/lava → `False`; chest (solid wooden-box stand-in) → `True`.
  - Missing assets → fallback magenta cube → `True` (full cube).
  - Otherwise: `True` **iff** (a) the union of the resolved elements' `from`/`to` boxes covers the full `[0,0,0]–[16,16,16]` cube (reuse `_model_applications` + `_resolve_model_elements_and_textures`, lines 245/466-path; use raw unrotated boxes), **and** (b) every resolved face texture is opaque — i.e. `img.mode != "RGBA"` (recall `_load_texture_image`, line 211, already demotes fully-opaque RGBA to RGB, so `RGBA` ⟺ genuinely transparent pixels). This makes **glass / stained glass / ice non-occluding automatically**, matching vanilla.
  - **Explicit exception: leaves occlude** (`name.endswith("leaves")` → `True` even with transparent texture). Vanilla treats leaves as opaque cubes for AO (only the texture is cutout in fancy graphics). Flagged as verify-against-vanilla in §6.
- **Partial blocks** (stairs, slabs, walls, fences, lanterns, trapdoors, …) are non-occluding at cell level — they fail the full-cube test. This is a documented v0 simplification vs vanilla (which samples sub-cell shapes); it only means partial blocks don't *cast* AO onto neighbors. They still *receive* it.

### 2.2 Vertex AO sampling rule

New pure function `_vertex_ao_level(v_local, normal, cell, occ) -> int` (0–3), called per quad vertex in the `_render_view` draw loop where `wpts`, `normal`, and cell `(x,y,z)` are all in scope (lines ~793–810):

- Let `a` = normal axis, `sa` = its sign; `t1, t2` = the two tangent axes (fixed order `(0,1,2) minus a` → deterministic).
- For tangent axis `t` with local coord `vt` (vertex minus cell, in [0,1], fractional allowed for partial-block quads):
  - `vt <= 1e-9` → neighbor offset `ot = -1` (vertex on min edge)
  - `vt >= 1 - 1e-9` → `ot = +1`
  - else (interior vertex, e.g. stair tread at 0.5) → `ot = 0` — sample the cell directly outside the vertex. Deterministic, no tie-break hacks.
- Sample the three cells in the face-adjacent layer (all indices into the padded `occ` grid, `+1` shift):
  - `side1 = occ[x+n_x + (ot1 if t1==0), …]` — offset `n` (the face normal cell step) plus `ot1·e_{t1}`
  - `side2` — `n` plus `ot2·e_{t2}`
  - `corner` — `n` plus both
- **Vanilla rule** (0fps/vanilla-derived, matches every community reimplementation): `level = 0 if (side1 and side2) else 3 - (side1 + side2 + corner)` with bools as ints.
- Enumerated sanity: open face → (0,0,0) → 3; one side → 2; one side + corner → 1; two sides → 0.

Vectorization (perf): per quad, build the 4×3 offset triples with plain Python arithmetic, then do **three fancy-index reads** on the padded bool array — no per-vertex Python loop over numpy scalars.

### 2.3 Brightness curve

New constant `_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)` for levels (0,1,2,3).

- **0.4 floor**: corroborated by community evidence — thelinuxseal/nanocraft commit (2026-09-26) "fix ambient occlusion treating air as solid": *"AO previously darkened nearly every vertex to 0.4"*, i.e. their vanilla-derived implementation's full-occlusion factor is 0.4.
- **Linear 0.2 steps**: the standard reconstruction of vanilla's per-level ramp used across vanilla-derived reimplementations. **Clearly labeled as a vanilla-derived approximation, not byte-verified from decompiled vanilla** — a single tunable constant, easy to retune if phase-2 in-game comparison says otherwise.
- **Composition with `_SHADES`: MULTIPLY, don't replace.** Vanilla's pipeline composes directional face shading and per-vertex AO multiplicatively, and `_SHADES` already matches vanilla's face-shading constants exactly (1.0/0.5/0.8/0.8/0.6/0.6). `_SHADES` stays baked into the cached texture (palette-level, view-independent); AO multiplies per-pixel at draw time: `final = texel × shade_face × ao_vertex`.

### 2.4 How AO flows into `_draw_textured_quad` (line 634)

- Signature becomes `_draw_textured_quad(canvas, pts_uv, tex, ao=None)` — `ao` = 4 brightness factors in `pts_uv` order (which matches `wpts` order 1:1 in the draw loop, lines ~800–806). Default `None` = all-1.0 → **byte-identical to current behavior** (keeps the direct unit test `test_draw_textured_quad_diamond_not_twisted` passing unchanged).
- In the draw loop: compute the 4 factors per quad; if all four are exactly `1.0` (the common open-face case — `_AO_BRIGHTNESS[3]` is defined as exactly `1.0`), pass `ao=None` (**fast path**: skips the brightness pass entirely, zero float error, isolated-block renders pixel-identical).
- When `ao` is given: after the existing warp, fit a **single affine** brightness function from the 4 `(sx,sy) → ao` correspondences via `lstsq` (same pattern as the existing texture fit), evaluate over the bbox with the existing `_ox/_oy` grids, `clip(0,1)`, and multiply into the warped RGB — **RGB only on the RGBA path** (alpha is transparency, same reasoning as `_shade_image`'s RGB-only shading, line 443). Truncation via `.astype(np.uint8)` matches `_shade_image`'s `int(v*factor)` semantics.
- Why affine (not bilinear) is exact here: every quad is an affine image of a planar rect (blockstate rotations are 90° multiples; element rotations are affine), so screen-space quads are parallelograms, where affine ≡ bilinear interpolation. `lstsq` on 4 parallelogram corners is exact, not approximate.
- **Deliberate non-goal**: vanilla's quad-diagonal flip (anisotropy fix) is unnecessary with whole-quad affine interpolation — no triangle split exists to flip. Noted as a possible refinement only if visual artifacts appear.

### 2.5 Precise change locations (file `src/mcbuilder/preview_faithful.py`, git `ab39e88`)

| # | Location | Change |
|---|----------|--------|
| 1 | After `_SHADES` (line ~114) | Add `_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)` + comment citing the approximation status and the nanocraft floor evidence |
| 2 | New section after `_resolve_model_elements_and_textures` (line ~280) | `_block_occludes_ao(canonical, assets_root, tex_cache) -> bool` (full-cube + opaque-texture rule, leaves exception, fluid/chest/air handling) |
| 3 | New section near §2 | `_vertex_ao_level(v_local, normal, occ_padded, cell) -> int` (pure sampler, §2.2 rule) |
| 4 | `_draw_textured_quad` (line 634) | Add `ao=None` param; brightness-mask array alongside the polygon mask; RGB-only multiply (both RGB and RGBA paths) |
| 5 | `_render_view` quad collection (lines ~761–790) | Build padded `occ` grid once per call from palette (passed in from `render()`); keep quad tuple shape unchanged |
| 6 | `_render_view` draw loop (lines ~793–810) | Compute 4 AO factors per quad from `wpts`/`normal`/cell; pass to `_draw_textured_quad`; fast path when all 1.0 |
| 7 | `render()` (line 873) | Compute palette-aligned `occ_idx` once (reuses `tex_cache`), pass into `_render_view` |

`resolve_block_quads` (line 610) return contract `(quads, is_fallback)` is **unchanged** — AO is cell/neighbor-dependent and cannot live in the palette-level quad cache. `render()`'s `RenderResult`/`info` shape unchanged.

## 3. Performance estimate & mitigations

- **Opacity grid**: O(palette entries) model resolutions, once per `render()` — reuses `tex_cache`; negligible (dozens of entries even at windmill scale).
- **Sampling**: 4 verts × 3 lookups per quad, but as 3 vectorized fancy-index reads per quad on a padded bool array — ~µs per quad; 10k quads ≈ tens of ms.
- **Brightness mask**: only for quads with *any* darkening (fast path skips the rest): one 4-point `lstsq` (~10µs) + one vectorized multiply-add over the bbox — roughly +30–60% of the existing warp cost for affected quads only.
- **Mitigations summary**: (1) palette-level opacity precompute, (2) padded-array vectorized sampling, (3) all-1.0 fast path skipping the brightness pass, (4) no per-view recomputation (`occ` built once in `render()`, passed to `_render_view`).
- **Determinism**: all pure functions of `(arr, palette, quads)`; fixed tangent-axis order; `lstsq` on identical inputs is bit-deterministic; no randomness, no dict-order dependence (iterate palette indices in order), sort keys untouched.

## 4. Regression test plan (new tests in `tests/test_preview_faithful.py`)

Existing suite is structural (no golden PNG bytes) — the sensitive ones are `test_stair_row_notches_are_real_geometry` (stairs are partial → non-occluding → that scene gets zero AO change; bg-fraction assertion unaffected) and `test_lantern_crossbars_no_black_smear` (isolated block → all-AO-3 → fast path → pixel-identical). Phase 2 must run the full 390 and specifically re-check these two.

New tests:
1. **`test_ao_open_face_uniform`**: isolated stone cube → top-face pixels all identical RGB (no gradient on an open face); equivalently, `_draw_textured_quad(..., ao=None)` vs `ao=(1,1,1,1)` → identical canvas.
2. **`test_ao_inner_corner_darkens`**: floor + wall forming an inside corner (e.g. 3×1×3 stone floor with a 3-high stone wall along one edge); render from iso; assert mean brightness of a patch at the wall/floor inner corner is **strictly less** than a patch at an outer edge of the same face.
3. **`test_ao_level_sampler_unit`**: direct `_vertex_ao_level` checks — all-air → 3; one side → 2; side+corner → 1; both sides → 0; interior-vertex (`vt=0.5`) rule → samples the cell directly outside.
4. **`test_ao_occlusion_classification`**: with fake assets — full opaque cube → True; glass-like (RGBA texture) → False; slab/stairs (partial) → False; `*leaves` (RGBA texture) → True; water/lava → False; air → False.
5. **`test_ao_deterministic`**: render a mixed grid twice → identical PNG bytes (md5).
6. **`test_ao_perf_smoke`**: synthetic 12×12×12 mixed stone/air grid via `FakeGrid` renders within a bound (propose: absolute wall-time bound calibrated in phase 2 against the pre-AO baseline, e.g. < 2× baseline; measure on this VM, don't guess).

## 5. Risks / open questions

1. **Brightness curve is an approximation** (0.4 floor corroborated, linear ramp assumed). Validation option for phase 2: place a 2×2×2 stone corner on Nile (Lost SMP is live) and eyeball against a vanilla client with smooth lighting on — manual, not automated.
2. **Partial blocks don't cast AO** (cell-level sampling can't see sub-cell shapes) — vanilla would darken a wall next to a stair's tall half. Documented v0 gap; fixing needs shape-aware sampling (future).
3. **Leaves-occlude decision** follows vanilla (`isOpaqueCube`-equivalent) but contradicts the "transparent texture" heuristic — kept as an explicit exception; if it looks wrong in practice, one-line change.
4. **Painter's-order interplay**: AO is computed per quad independently of draw order, so sort order can't corrupt it. Translucent quads (fluids) receive AO like everything else — slight deviation from vanilla (which skips AO on fluids) but visually coherent; flagged, not blocked.
5. **Anisotropy**: skipped per §2.4; if corner gradients look "twisted" on some quad, revisit.
6. **`test_stair_row_notches_are_real_geometry`** compares faithful vs trusted bg fractions — AO must not be ported to the trusted tier in this change (it isn't), and the scene's stairs cast nothing, so parity holds; re-run to confirm.

## 6. Confirmation

- **Direction-trust guarantees untouched**: no changes to vertex positions, normals, UV corner assignment/painting, `_order_corners_uv`, rotation helpers, variant/multipart selection, culling, or sort keys. The diff is purely photometric (per-pixel brightness), applied after all geometry is final.
- **390 existing tests must stay green**: no existing function signatures break (`ao` is an optional param; `resolve_block_quads`/`render` contracts unchanged); the all-1.0 fast path keeps isolated-block renders pixel-identical; phase 2 runs the full suite on branch `acc/smooth-lighting` before any merge consideration.
