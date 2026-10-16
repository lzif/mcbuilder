# CONSOLIDATED PHASE-1 PLAN — mcbuilder faithful-renderer accuracy gaps

**Status:** IMPLEMENTED & MERGED (2026-10-10) — all four gaps shipped on `main`: `acc/fluid-height` (`dcc73c5`), `acc/biome-tint` (`8d2d9e8`), `acc/block-entities` (`f3f95f2`), `acc/smooth-lighting` (`d0373ef`). This document is retained as the design rationale; the per-gap sections are historical plans, not pending work.
**Base (at planning):** `main` @ `ab39e88` (390 tests green). **Client assets:** `~/.cache/mcbuilder/26.2/`.
**Full per-gap detail:** `~/workspace/mcbuilder/plan-acc/gap{1,2,3,4}-*-v2.md` (gap3 is v1 — needed no revision).

## Global constraints (all gaps)
- 390 existing tests must stay green after every merge (`cd ~/workspace/mcbuilder && .venv/bin/python -m pytest tests/ -q`).
- Each gap adds regression tests (listed per gap).
- No AI/tool attribution anywhere git-facing (commits, messages, comments) — standing rule.
- Follow existing code style; keep the renderer's direction-trust guarantees intact (tint/AO/fluid-height are color/geometry refinements that must not alter orientation logic; block-entities EXTENDS direction-trust with per-facing tests).
- Implementation on per-gap branches: `acc/biome-tint`, `acc/smooth-lighting`, `acc/fluid-height`, `acc/block-entities`; merge sequentially with pytest after each merge (phase 2, starts only on explicit lock).

## Merge order: gap3 → gap1 → gap4 → gap2
- **gap3 first:** smallest blast radius; establishes `_fluid_cube_quads(rgba, top_height)` which gap4's chest-exclusion builds on.
- **gap1 second:** independent of gap3; touches `_FLUID_FLAT` water value before gap4 adds keys to the same dict.
- **gap4 third:** hook placement written against gap3's fluid branch; fast-tier colors land on top of gap1's water change.
- **gap2 last:** the AO classifier is written merge-order-independent (dispatch-mirroring + `hasattr` guard), but writing it last means it sees the final dispatch.

## Review trail
A fresh-context reviewer verified all v1 plans against the real source at ab39e88. Findings fixed in rev 2:
- gap2: H1 (quad tuple had no normal — tuple extended to 10 items), M1/C1 (classifier now mirrors `resolve_block_quads` dispatch, entity-aware, merge-order-independent), M2 (explicit ice/slime/honey non-occluding set), M3 (`None` textures → opaque, no crash), plus line-number refresh and signature consistency.
- gap4: H2 (fast-tier `_FLUID_FLAT` now skips `fallback_blocks.add` — with water/lava behavior-change note), M6 (tripwire `attached=` correction), M8 (blocking pre-merge visual gate), M12 (wall-banner mapping reframed as inferred).
- gap1: M4 (flowerbed `tintindex: 1`, new `>= 0` gating test), M5 (fast-tier bamboo limitation documented + pinned), M9 (fixtures move to conftest), M11 (3-unpack spelled out), L5 (two-north-quad test disambiguation).
- gap3: approved nearly as-is.

---

## GAP 3 — Fluid height (`acc/fluid-height`) — plan v1, review-clean

**Vanilla value (verified, cited):** still-fluid surface with no same-fluid above = **exactly 8/9 ≈ 0.8888889**.
Sources: minecraft_clone water-rendering research docs, measured from the official Java 1.21.4 client decompiled with CFR/Yarn mappings — "MAX_FLUID_HEIGHT = 0.8888889, exactly 8.0/9.0"; source block amount 8 → 8/9. Lava: no lava-specific quote found, but vanilla runs both fluids through the same fluid renderer operating on `FluidState` (fluid-agnostic) — **apply 8/9 to both water and lava** (most defensible; lava-at-1.0 would contradict the shared renderer).

**Changes** (all in `src/mcbuilder/preview_faithful.py`):
1. New constant near `_FLUID_RGBA` (:581): `_FLUID_SURFACE_HEIGHT = 8.0 / 9.0` with derivation comment.
2. `_fluid_cube_quads(rgba, top_height: float = 1.0)` (:591): per-face bounds — `t = (1.0, top_height if face_name == "up" else 1.0, 1.0)`; `_face_base_corners` (:398) builds corners from `f`/`t` directly so only the 4 top corners lower. Shading/UV unchanged (top face is a flat RGBA color, no texture sampling).
3. `resolve_block_quads` (:617–619): `top_h = _FLUID_SURFACE_HEIGHT if name in ("minecraft:water", "minecraft:lava") else 1.0` → `_fluid_cube_quads(_FLUID_RGBA[name], top_height=top_h)`. Chest (also in `_FLUID_RGBA`) explicitly excluded → stays 1.0. Default `1.0` keeps chest byte-identical.
4. No `_draw_textured_quad` / `_render_view` changes (normals unchanged; RGBA compositing unaffected).

**Fast tier (`preview.py`): scoped OUT** — its contract is fast/approximate flat cubes through a shared geometric path; lowering tops there = higher regression risk for the wrong tier. Optionally revisit separately.

**Edge decisions:** side faces stay full 0..1 (vanilla clips them too, but that needs neighbor context the per-palette quad cache doesn't have — documented approximation); down face unchanged; same-fluid-above (vanilla 1.0) not modeled (uniform 8/9; terraced columns accepted + documented); flowing `level` ignored this phase (still-only scope; vanilla flowing heights need per-corner neighbor averaging); no z-fighting guard needed (8/9 < 1.0 strictly).

**Tests** (`tests/test_preview_faithful.py`): water top quad normal (0,1,0) all y ≈ 8/9 (`pytest.approx`) and max y < 1.0; sides still span 0..1; down at y=0; lava same; chest top == 1.0 exactly; `water[level=1]` renders at 8/9 (documents still-only scope); top quad RGBA alpha 150/210 preserved; render smoke test; determinism (two calls identical). No existing test references fluids — all net-new.

**Direction-trust:** untouched — the fluid path bypasses the orientation pipeline entirely.

---

## GAP 1 — Biome tint (`acc/biome-tint`) — plan rev 2

**Goal:** honor `tintindex` from model JSONs; sample colormaps for the **plains** default biome; multiply into face textures. Both tiers.

**Verified plains values** (PIL reads from real 26.2 colormaps; plains.json t=0.8/h=0.4 → pixel (50,173) via vanilla `ColorMapColorUtil` formula, cross-checked against wiki inventory tint):
- grass `#91BD59` (145,189,89) · foliage `#77AB2F` (119,171,47) · dry foliage `#A37546` (163,117,70) · water `#3F76E4` (63,118,228)
- Fixed: birch `#80A755` (128,167,85), spruce `#619961` (97,153,97), lily pad `#208030` (32,128,48).
- Dry-foliage discrepancy resolved: fmcmapper README's `#7B4F19` exists nowhere in the 26.2 file; `#A37546` kept, with in-game eyeball backstop.

**Verified tintindex facts:** grass_block up+4 overlay faces = 0 (base sides untinted — pre-tinted fast-graphics texture); `leaves.json` all 6 faces = 0 (cherry/pale_oak inherit but get NO tint — default-deny); tinted_cross/vine/potted_fern/lily_pad/leaf_litter = 0; **flowerbed_1 `#stem` faces = 1** (gating is `>= 0`); bamboo stalk untinted, leaf models tinted.

**Tint table** (`_TINT_TABLE` in `preview.py`, shared via `_fast`): grass colormap → grass_block, short/tall_grass, fern, large_fern, potted_fern, sugar_cane, bush, wildflowers, pink_petals, bamboo (medium-confidence ones flagged); foliage → oak/jungle/acacia/dark_oak/mangrove leaves + vine; dry foliage → leaf_litter; fixed → birch/spruce/lily_pad. **Default-deny:** not in table → no tint even with `tintindex` (mirrors vanilla's white default).

**Changes:**
- `preview.py` (~:340): plains constants + `_TINT_TABLE` + `_tint_image(img, rgb)` (RGB multiply, alpha preserved, returns NEW image — mirrors `_shade_image`).
- `_FLUID_FLAT`: water `(52,120,235)` → `(63,118,228)` (no test asserts old value).
- `_do_resolve` (~:213): collect `tinted_vars` (post-`#` texture-var names referenced by faces with `tintindex >= 0`); arity 2→3 — **explicitly update all return points AND both call sites** (`:550` fallback init, `:552` the real call → 3-unpack) and the `_resolve_model_textures` wrapper exception path.
- `_build_face_textures` (~:546): non-fallback branch only — `if var in tinted_vars and (tint := _TINT_TABLE.get(name)) is not None: img = _tint_image(img, tint)`.
- `preview_faithful.py` `_resolve_block_quads` face loop (~:511, after UV-rotation crop, before shading): `ti = face.get("tintindex", -1)`; tint only if `has_real_texture` (fallback flat colors stay untinted) and `ti >= 0` and table hit. **Cache safety:** tint applies to the per-face `.crop()` (fresh image) — `tex_cache` never mutated.
- `_FLUID_RGBA`: water `(52,120,235,150)` → `(63,118,228,150)` (hue only; alpha 150 kept).

**Known fast-tier limitation — bamboo (documented, pinned):** `_do_resolve` resolves only the FIRST multipart apply (`:233-240`); `bamboo.json` orders untinted stalk models first → fast-tier bamboo never tints. Unioning rejected as unsound (var names are model-local). Faithful tier iterates all cases and tints correctly.

**Tests** (new `tests/test_biome_tint.py`; hermetic — no real-cache dependency):
0. Move `assets_root`/`tex_cache` fixtures + helpers from `test_preview_faithful.py:122-128` into `tests/conftest.py` first; run suite to prove no behavior change. Extend `make_assets` with tint fake models (solid-color textures for exact pixel assertions).
1. Pinned table values. 2. Overlay analog: exactly 2 north quads, one tinted + one untinted (mirrors real grass block). 3. Leaves analog: all 6 faces tinted; two blocks sharing one texture with different table colors → different quad means. 4. Untinted controls (no-table stone analog; cherry analog with inherited tintindex but no entry). 5. Cache isolation (cached sources byte-identical to raw PNGs). 6. Fast tier: up tinted, untinted var raw; `_fallback_color("minecraft:water") == (63,118,228)`. 7. Water top-face pixel == `(63,118,228,150)`. 8. `tintindex: 1` faces tinted (wildflowers gating). 9. `test_tint_multi` → fast-tier `tinted_vars == set()` (pins bamboo limitation). 10. Full 390 green.

**Out of scope:** per-biome selection, redstone/stem tints, cauldron water, asset-pipeline changes. Redstone/stem limitation documented in a code comment.

---

## GAP 4 — Block entities (`acc/block-entities`) — plan rev 2

**Key finding:** the gap is smaller than assumed — standing/wall/hanging signs ALREADY render via vanilla template JSON models. Remaining work: chest family (11 names), banners (32), + one-line `_DEFAULT_PROPS` fix for bare signs.

**Changes** (`src/mcbuilder/preview_faithful.py`, new section between `_fluid_cube_quads` :591 and `resolve_block_quads` :610):
- `_ENTITY_TEXTURES`: block name → texture rel (`"entity/chest/normal"` etc.). Chest: normal/trapped/ender/copper/exposed/weathered/oxidized + waxed→unwaxed-stage mapping (all 64×64, verified in 26.2 jar). Banners: suffix-matched, single `entity/banner/banner_base.png` (cloth + pole + bar regions, pixel-verified).
- `_try_entity_quads(name, props, root, tex_cache) -> list | None` — `None` = not entity-approximated OR texture missing/wrong-size → falls through to existing behavior (chest → wooden box; others → magenta).
- Hook in `resolve_block_quads`, **before** the `_FLUID_RGBA` check, guarded by `assets_root is not None`; returns `(quads, False)` — intentional approximation, no fallback warning. Must preserve gap3's `top_h` name-keying and stay above the fluid dispatch.
- `_entity_box_quads(f, t, face_uvs, img)` — generic box builder on `_face_base_corners`/`_order_corners_uv`/`_shade_image`/`_SHADES`; painted-on UVs in canonical orientation before rotation.
- `_chest_quads`: body (1/16,0,1/16)→(15/16,10/16,15/16), lid →(15/16,15/16,15/16), latch (7/16,11/16,0)→(9/16,15/16,1/16); 13-row UV table (pixel-verified); canonical latch north; `facing` → `_rot_y` {n:0,e:90,s:180,w:270}; bare chest → north via `_DEFAULT_PROPS`. Asserts 64×64 else `None`.
- `_banner_quads`: standing (pole + crossbar + hanging cloth, canonical south, `rotation`×22.5° via NEW `_rot_y_degrees` — cos/sin, clockwise-from-above, same convention as `_rot_y`); wall (crossbar + cloth, `facing` → {s:0,w:90,n:180,e:270} — **inferred by sign-template analogy**, `white_wall_banner.json` has no facing variants); cloth tinted by 16 dye RGBs (white base verified near-white); **no patterns** (stated limitation).
- `preview.py:169` `_DEFAULT_PROPS` += `"rotation": "0"`, `"attached": "false"` — fixes bare `oak_sign`/`oak_hanging_sign` (also fast tier). **Corrected risk note:** `tripwire.json`/`tripwire_hook.json` DO key on `attached=` (32/16 variants) — benign because those variant keys also require props absent from defaults (`_match_variant` :181); put a re-audit warning in a code comment. `rotation` default genuinely safe (no non-sign blockstate keys on it).
- `assets.py:46`: add `"assets/minecraft/textures/entity/"` to `_CLIENT_PREFIXES` (~hundreds of KB). Idempotency caveat: existing caches lack entity textures until cache deletion — graceful fallback covers it; tests must cover the missing-texture path.

**Fast tier:** NO geometry (contract = flat cubes); add honest colors to `_FLUID_FLAT`: chest (181,140,82), trapped (170,110,75), ender (60,55,70), copper family (200,120,70), 16 dye RGBs for banners. **Plus the H2 code change:** skip `fallback_blocks.add(name)` when `name in _FLUID_FLAT` in `_build_face_textures` — **behavior change:** water/lava STOP appearing in fast-tier `fallback_blocks`; note in merge commit body.

**Tests** (`test_preview_faithful.py` + `test_preview.py`): chest not-fallback (≥15 quads, textured); lid-above-body y-ranges; latch centroid per facing {n,e,s,w} (direction-trust); per-variant textures; missing-texture fallback chain incl. `assets_root=None`; banner not-fallback (≥10 quads); cloth tint (red-dominant / near-white); standing rotation {0→+Z, 4→−X, 8→north}; wall-banner facing (centroid + normal); bare signs resolve; wall-sign board faces facing; fast-tier flat colors + NOT in `fallback_blocks` (chest/banner/water/lava); `_rot_y_degrees` ≡ `_rot_y` at 90° multiples (new); full 390 green.

**⛔ BLOCKING pre-merge visual gate:** per-facing tests pin orientation, NOT texture-region correctness — the chest UV table / banner regions / latch geometry are the highest-risk unverifiable content (entity textures were never in the cache). Before merge: render approximations (chest front/side/top incl. latch, banner front/back incl. tinted color, all facings) and eyeball against in-game screenshots. Do NOT merge on green tests alone. Needs Luki (server reference screenshots).

**Out of scope:** double chests, shulker boxes, Christmas textures, banner patterns, sign text, beds/skulls.

---

## GAP 2 — Smooth lighting / AO (`acc/smooth-lighting`) — plan rev 2, merge LAST

**Scope:** `preview_faithful.py` only. Lighting-only — no vertex positions, normals, UVs, sort keys, or culling change.

**Verified baseline (ab39e88):** quad pipeline `_resolve_block_quads` :466; `_SHADES` :103 (1.0/0.5/0.8/0.8/0.6/0.6); NO occlusion classification exists anywhere; collect loop appends 9-tuple `(depth,x,y,z,seq,wpts,tex,_is_fallback,block)` at **:833** (no normal — rev 1 misread this); draw loop unpacks 9 at **:839**; sort key `:836` on indices 0–4; `_draw_textured_quad` :634 called at :847 AND directly by tests (:405, :470).

**Design:**
1. **`_block_occludes_ao(canonical, assets_root, tex_cache) -> bool`** (new, after `_resolve_model_elements_and_textures` :245) — computed once per `render()` per palette entry → bool array → padded cell grid (`arr.shape+2`, OOB = air). **Mirrors `resolve_block_quads` dispatch exactly** (merge-order-independent):
   - UNSET/air → False. `_FLUID_RGBA`: water/lava → False, chest → True. `assets_root None` → True.
   - **Entity path** guarded by `hasattr(module, "_try_entity_quads")` (pre-gap4: skipped; banner/chest fall to model/fallback path, matching render). When present: returns quads → banner-kind (`endswith("_banner")`) → False (thin cloth must not cast like a cube); chest-family → True (near-full box). Returns `None` → fall through (matches render degradation).
   - **Explicit non-occluding set** `{ice, slime_block, honey_block}` → False (before texture heuristic; load-bearing for the None-texture case; documents vanilla semantics).
   - **Model path:** True iff element `from`/`to` union covers full [0,0,0]–[16,16,16] (raw unrotated boxes via `_model_applications` :333) AND every face texture opaque (`img is None` → opaque — renderer degrades to opaque flat RGB — or `img.mode != "RGBA"`; `_load_texture_image` :211 demotes fully-opaque RGBA→RGB so RGBA ⟺ genuinely transparent). Glass/stained glass → non-occluding automatically. **Leaves → True** (explicit exception; vanilla treats leaves as opaque for AO).
   - Model resolution fails → True (magenta cube).
   - Partial blocks (stairs/slabs/walls/…) → non-occluding at cell level (documented v0 simplification; they still RECEIVE AO).
2. **`_vertex_ao_level(v_local, normal, cell, occ_padded) -> int`** (canonical signature): tangent axes in fixed order; per-axis neighbor offset from vertex position (`<=1e-9`→−1, `>=1−1e-9`→+1, else 0); sample side1/side2/corner in the face-adjacent layer; **vanilla rule** `level = 0 if (side1 and side2) else 3 − (side1+side2+corner)`. Vectorized: 3 fancy-index reads per quad.
3. **`_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)`** (after `_SHADES` :103) — 0.4 floor corroborated by nanocraft commit; linear ramp honestly labeled vanilla-derived approximation; single tunable constant. **Composes with `_SHADES` by MULTIPLY** (shade stays baked palette-level; AO multiplies per-pixel at draw: `texel × shade × ao`).
4. **`_draw_textured_quad(canvas, pts_uv, tex, ao=None)`** (:634): `ao` = 4 factors in `pts_uv` order (= `wpts` order). `None`/all-1.0 → **fast path, byte-identical** (existing 3-arg test calls keep passing). Else: single affine brightness fit via `lstsq` (exact on parallelograms — all quads are affine images of planar rects), evaluated on existing `_ox/_oy` grids, `clip(0,1)`, multiplied into warped RGB only (alpha untouched, same reasoning as `_shade_image`). `.astype(np.uint8)` truncation matches `_shade_image` semantics. Diagonal-flip deliberately skipped (no triangle split exists).
5. **Tuple extension:** collect :833 → 10-tuple `(depth,x,y,z,seq,wpts,normal,tex,_is_fallback,block)`; sort key :836 untouched (indices 0–4); draw loop :839 unpacks `for _, x, y, z, _, wpts, normal, tex, is_fb, block in quads:`; fix stale comment at :808. `render()` :873 computes `occ_idx` once (reuses `tex_cache`), builds padded grid, passes into `_render_view` (:761, new `occ_padded` param — internal, no external callers).

**Perf:** palette-level precompute (negligible); ~µs/quad sampling (10k quads ≈ tens of ms); brightness pass only for darkened quads (+30–60% of warp cost for those); no per-view recompute. **Determinism:** pure functions, fixed axis order, `lstsq` bit-deterministic, no dict-order dependence.

**Tests** (`test_preview_faithful.py`): open-face uniform (isolated cube; `ao=None` vs `(1,1,1,1)` identical); inner corner strictly darker than outer edge; sampler unit (3/2/1/0 + interior-vertex rule); classification extended (opaque→True, glass RGBA→False, partial→False, leaves→True, fluids→False, air→False, **ice/slime/honey→False, None-texture→True no-crash**); **tinted-leaves composition** (tint × 0.4, alpha untouched); **entity classification** (`hasattr`-conditional: trapped_chest→True, white_banner→False; else both→True); determinism (md5 of two renders); perf smoke (< 2× pre-AO baseline, measured on-VM). Re-check `test_stair_row_notches_are_real_geometry` and `test_lantern_crossbars_no_black_smear` explicitly.

**Risks:** brightness curve is approximate → phase-2 in-game eyeball on Nile (2×2×2 stone corner vs vanilla smooth lighting); partial blocks don't cast; fluids receive AO (vanilla skips — visually coherent, flagged); tinted-glass AO behavior unverified → include in eyeball check.

---

## Cross-plan composition (all verified compatible)
- Tint × AO: multiplicative at different stages (tint → face shade → AO) — matches vanilla order. No action.
- Tint × fluid-height: different lines of `_FLUID_RGBA` (color vs geometry); tests pin orthogonal properties. No action.
- Fluid-height × block-entities: adjacent edits in `resolve_block_quads` head; gap4's hook stays above the fluid dispatch and preserves `top_h` name-keying. Merge order handles it.
- Tint × block-entities: `_FLUID_FLAT` same dict (gap1 water value, then gap4 keys — order matters, handled by merge order); entity quads bypass `_resolve_block_quads` face loop so never hit the tint path (not in `_TINT_TABLE`; banner dye tint is separate). No action.
- AO × tint: tint never mutates `tex_cache` (fresh crops); classifier is read-only over it. No cache invalidation issue.
- AO × block-entities: handled by the dispatch-mirroring classifier (C1) — the one HIGH cross-plan conflict, resolved in rev 2.

## Shared-code edit sites (merge cleanly in the recommended order)
`resolve_block_quads` head (gap3+gap4) · `_FLUID_RGBA` water entry (gap1+gap3) · `_FLUID_FLAT` (gap1+gap4) · `_draw_textured_quad` signature (gap2 only) · `_do_resolve`/`_resolve_model_textures` arity (gap1 only) · `_render_view` collect/draw loop (gap2 only) · `_DEFAULT_PROPS` (gap4 only) · `assets.py` `_CLIENT_PREFIXES` (gap4 only) · `tests/conftest.py` fixtures (gap1 only).
