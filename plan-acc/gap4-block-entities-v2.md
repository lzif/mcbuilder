# Plan: Block-Entity Approximations (chest / banner) — faithful tier — REVISED v2 (2026-10-10, post fresh-context review)

**Branch (phase 2):** `acc/block-entities` · **Base:** main @ ab39e88 · **Tests:** 390 must stay green
**Merge position:** third (after fluid-height → biome-tint). **Implementation later** — phase 1 is plan only.

## Revisions vs v1 (2026-10-10, post fresh-context review)

- **H2:** §7 now carries an explicit `_build_face_textures` code change — skip `fallback_blocks.add(name)` when `name in _FLUID_FLAT`. Behavior change called out: `minecraft:water`/`minecraft:lava` will **stop** appearing in fast-tier `fallback_blocks`, altering `info` output consumers may rely on. Test #12 updated to pin the new behavior.
- **M6:** §4 "zero risk" claim corrected — `tripwire.json` (32 variants) and `tripwire_hook.json` (16) DO key variants on `attached=`; benign via `_match_variant` reasoning (below), with a warning that future defaults additions need re-audit. The `rotation` default stays genuinely safe — no non-sign blockstate in the 26.2 cache keys on `rotation=`.
- **M8:** new §12 work order with a **blocking pre-merge visual gate** — render the approximations and eyeball them against in-game screenshots (chest front/side/top, banner front/back) before merge.
- **M12:** wall-banner facing mapping reframed from "verified" to "inferred by sign-template analogy"; in-game check retained.
- New missing tests: **test 13** (`_rot_y_degrees` ≡ `_rot_y` at 90° multiples); **test 5 extended** with the `assets_root=None` case (hook skipped by guard → wooden box).

## 0. Key findings — the gap is smaller than assumed

Verified by running `resolve_block_quads` against the real 26.2 cache (`~/.cache/mcbuilder/26.2/client/assets/minecraft`):

| Block | Current behavior | Verdict |
|---|---|---|
| `oak_sign[rotation=3]` | 11 textured quads, `is_fallback=False` | ✅ Already renders — vanilla ships real JSON models (`models/block/template_sign_rot_0..3.json`) with true elements + UVs into `textures/block/oak_sign.png` (32×32, already in cache) |
| `oak_wall_sign[facing=north]` | 6 quads, not fallback | ✅ Already renders (`template_wall_sign.json`) |
| `oak_hanging_sign[attached=false,rotation=0]` | 14 quads, not fallback | ✅ Already renders (`template_hanging_sign*.json`) |
| `oak_sign` (bare, no props) | magenta fallback | ❌ Gap is **not geometry** — `_DEFAULT_PROPS` (preview.py:169) lacks `rotation`/`attached`, so no variant matches |
| `minecraft:chest` | flat wooden box, `is_fallback=False` | ⚠️ Works but orientation-blind (no facing handling) and untextured |
| `trapped_chest`, `ender_chest`, `copper_chest` (+ variants) | magenta fallback | ❌ Needs work |
| `white_banner`, `white_wall_banner` | magenta fallback | ❌ Needs work (`models/block/banner.json` has particle only, no elements) |

**Sign textures are NOT entity textures** — there is no `textures/entity/signs/` in 26.2; signs use `textures/block/<wood>_sign.png` (already downloaded). Only **chest** (`textures/entity/chest/*.png`) and **banner** (`textures/entity/banner/*.png`) need entity textures, which the asset pipeline does **not** currently extract (`assets.py:46` `_CLIENT_PREFIXES` = `textures/block/`, `models/block/`, `blockstates/` only).

## 1. Design: entity-approximation dispatch

New section in `src/mcbuilder/preview_faithful.py` between `_fluid_cube_quads` (line 591) and `resolve_block_quads` (line 610):

- `_ENTITY_TEXTURES: dict[str, str]` — block name → texture rel (for `_load_texture_image`, e.g. `"entity/chest/normal"`). Chest family (11 names); banners matched by suffix (see §3).
- `_try_entity_quads(name, props, root, tex_cache) -> list | None` — returns textured quads, or `None` when the block isn't entity-approximated **or** its texture failed to load (missing file, wrong size). `None` = fall through to existing behavior.
- Hook in `resolve_block_quads` (line 610), **before** the `_FLUID_RGBA` check:
  ```python
  if assets_root is not None:
      entity_quads = _try_entity_quads(name, props, assets_root, tex_cache)
      if entity_quads is not None:
          return entity_quads, False   # intentional approximation, no fallback warning
  ```
  Fallback chain on missing entity texture is then automatic and identical to today: `chest` → wooden box via `_FLUID_RGBA` (line 581); `trapped/ender/copper_chest`, banners → magenta cube. No new warnings invented.
- **Composition with the fluid-height gap:** that gap lands first in the merge order. The entity hook stays a plain name-based check placed before the fluid dispatch, so there is no interaction — the hook must not move below the fluid-height dispatch, and must preserve the fluid gap's `top_h` name-keying for water/lava.
- Generic box helper reusing the existing quad machinery:
  ```python
  def _entity_box_quads(f, t, face_uvs, img):
      # f, t: block-local 0–1 box corners; face_uvs: face -> (x0,y0,x1,y1) pixel rect
      # returns [(ordered_points, world_normal, shaded_crop)] in the standard quad format
  ```
  Built on `_face_base_corners` (398) + `_order_corners_uv` (412) + `_shade_image` (443) + `_SHADES` (103) + `_FACE_NORMALS` (112). Corners are ordered in canonical orientation **before** any facing/rotation transform (painted-on, same rule as the model path). Faces absent from `face_uvs` are skipped (e.g. pole bottom).
- Orientation helpers:
  - 90° steps: reuse `_rot_y` (141) for points and `_rot_y_dir` (149) + `_snap_normal` (382) for normals.
  - NEW `_rot_y_degrees(p, degrees)` (cos/sin, clockwise-viewed-from-above, same convention as `_rot_y`) for standing-banner `rotation` (22.5° steps). Normals rotated then `_snap_normal`'d — identical to how diagonal sign boards already behave via element rotation + `_snap_normal`.

## 2. Chest approximation — `_chest_quads(props, img)`

Geometry from the verified texture layout (chest `normal.png` is 64×64; side bands prove the model: lid band 14 wide × 5 tall, body band 14 wide × 10 tall — matches vanilla's 14×10×14 body + 14×5×14 lid; we render the visual model):

- **Body:** `(1/16, 0, 1/16)` → `(15/16, 10/16, 15/16)`
- **Lid:** `(1/16, 10/16, 1/16)` → `(15/16, 15/16, 15/16)`
- **Latch:** `(7/16, 11/16, 0)` → `(9/16, 15/16, 1/16)` (2×4×1 px, protrudes from lid front; all faces sample the metallic-gray region). The latch sits proud of the lid's front face, so no coplanar z-fighting.

UV regions. **Caveat (M8): `textures/entity/` was never extracted to the asset cache** (consistent with `_CLIENT_PREFIXES` lacking the entity prefix), so these regions are the highest-risk unverifiable content in this plan — the §12 pre-merge visual gate exists for exactly this:

| Part | Face | UV rect |
|---|---|---|
| Body | front(+Z) | (14,33)-(28,43) |
| Body | back(−Z) | (42,33)-(56,43) |
| Body | left(+X) | (28,33)-(42,43) |
| Body | right(−X) | (0,33)-(14,43) |
| Body | top | (14,19)-(28,33) |
| Body | bottom | (28,19)-(42,33) |
| Lid | front | (14,14)-(28,19) |
| Lid | back | (42,14)-(56,19) |
| Lid | left | (28,14)-(42,19) |
| Lid | right | (0,14)-(14,19) |
| Lid | top | (14,0)-(28,14) |
| Lid | bottom | (28,0)-(42,14) |
| Latch | all | (0,0)-(5,4) (metallic gray, verified bbox) |

Orientation: canonical latch on the **north** face; `facing` → `_rot_y` degrees `{north:0, east:90, south:180, west:270}` (verified: `_rot_y(90)` maps north-face-center → east-face-center). Bare `minecraft:chest` → `facing` default `north` via existing `_DEFAULT_PROPS`.

Texture map (all 64×64, verified present in 26.2 jar):
`chest→entity/chest/normal`, `trapped_chest→entity/chest/trapped`, `ender_chest→entity/chest/ender`, `copper_chest→entity/chest/copper`, `exposed_→copper_exposed`, `weathered_→copper_weathered`, `oxidized_→copper_oxidized`, `waxed_*` → same as unwaxed stage. Implementation asserts `img.size == (64,64)` else returns `None` (falls back).

## 3. Banner approximation — `_banner_quads(props, img, dye_rgb, wall)`

Single texture: `textures/entity/banner/banner_base.png` (64×64) — verified it contains cloth panels + pole wood + bar wood. Regions (pixel-verified; same M8 caveat as §2):

- Cloth front: **(1,1)-(21,41)**, cloth back: **(22,1)-(42,41)** (white, avg 242 — tintable)
- Pole wood strip: **(44,0)-(51,41)** (8×42 = 4 sides × 2px); sample 2px vertical crops, e.g. front (46,2)-(48,42)
- Bar wood strip: **(0,42)-(43,45)**; front face sample e.g. (12,42)-(32,44)

Geometry (block-local, simple in-game silhouette):
- **Standing** (`<color>_banner`): pole `(7/16,0,7/16)-(9/16,14/16,9/16)`; crossbar `(-2/16,12/16,7/16)-(18/16,14/16,9/16)` (20×2×2); cloth `(-2/16,2/16,7.5/16)-(18/16,12/16,8.5/16)` (20×10×1 hanging from the bar). Canonical faces **south**; `rotation` (0–15, default 0) → `_rot_y_degrees(rotation × 22.5)`.
- **Wall** (`<color>_wall_banner`): no pole — crossbar `(-2/16,12/16,0)-(18/16,14/16,2/16)`; cloth `(-2/16,2/16,0.5/16)-(18/16,12/16,1.5/16)`. Canonical faces **south**; `facing` → `{south:0, west:90, north:180, east:270}` — **inferred by analogy** with `oak_wall_sign`'s actual y-rotations (verified in `template_wall_sign.json`) and `_rot_y`'s clockwise-from-above convention, **not** blockstate-verified: `white_wall_banner.json` ships only the empty-string variant. In-game screenshot check in the §12 gate.
- **Color:** tint cloth crops by the banner's dye color (block-name prefix → 16 vanilla dye RGBs; white banner verified near-white base so multiply is correct). Tint via PIL split → `point(lambda v: v*c//255)` → merge, preserving alpha. **Limitation (stated): no patterns** — pattern layers (`Patterns` block-entity NBT) are not rendered; only the base color.
- Thin cloth edges (1px sides): sample a 2px edge column from the panel; top/bottom of bar/pole: reuse wood crops.

## 4. Signs — no new geometry (one-line fix, corrected risk note)

Standing / wall / hanging signs already render via vanilla template models. Only change: `preview.py:169` `_DEFAULT_PROPS` += `"rotation": "0"`, `"attached": "false"` so bare `minecraft:oak_sign` / `minecraft:oak_hanging_sign` resolve instead of magenta. This also fixes the fast tier's flat-cube texturing for bare signs (same shared dict).

**Corrected risk analysis (M6):** the v1 claim "no other blockstate keys variants on rotation/attached" was wrong. Verified in the 26.2 cache: `tripwire.json` ships **32 variants, all keying on `attached=`** and `tripwire_hook.json` ships **16 variants, all keying on `attached=`**. The outcome is still benign, but the reason is narrower: `_match_variant` (preview.py:181) only requires that every key-pair in a *variant key* be satisfied — those tripwire variant keys also require props like `east`/`west`/`north`/`south`/`powered` that are **not** in `_DEFAULT_PROPS`, so with bare props they still match nothing and behavior is unchanged. **Warning for future work:** this makes `_DEFAULT_PROPS` additions non-monotonic in reasoning terms — adding a default like `east: "false"` in a later change could silently start matching tripwire variants today that this change leaves unmatched. Re-audit on every defaults addition (put this in a code comment). The `rotation` default is genuinely safe: **no non-sign blockstate in the 26.2 cache keys on `rotation=`** (skulls use the empty-string variant).

## 5. Asset pipeline — `src/mcbuilder/assets.py:46`

Add `"assets/minecraft/textures/entity/"` to `_CLIENT_PREFIXES`. Note the idempotency caveat: `fetch` returns early when `blockstates/` is populated, so **existing caches won't get entity textures until the cache dir is deleted** — the `_try_entity_quads → None` fallback path (§1) covers this gracefully (phase-2 tests must cover the missing-texture path). `textures/entity/*` is small (~hundreds of KB) — negligible download growth. `_load_texture_image` (preview_faithful.py:211) is reused **unchanged**: `rel="entity/chest/normal"` resolves to `textures/entity/chest/normal.png` under the same root. No `.mcmeta` animation handling needed (none of these textures are animated).

## 6. Composition notes

- **Shading:** every quad carries a world-space outward normal → `_SHADES` lookup applies exactly as today; diagonal banner normals snap via `_snap_normal` (shade 0.75 fallback for non-axis, same as diagonal signs today).
- **Translucency:** all approximations are **opaque**. Entity PNGs load as RGBA (transparent regions elsewhere in the file) but our crops are fully-opaque regions; the existing `_draw_textured_quad` RGBA path handles them (alpha 255 → normal paste).
- **AO:** no AO exists in the renderer today (sign templates ship `"ambientocclusion": false`); our quads are standard `(points, normal, image)` format, so any future per-face AO composes without changes. Order-independence assumed and preserved.
- **Caching:** `resolve_block_quads` results are cached per palette index in `_render_view` — entity quads cost one resolve per block type, same as models.

## 7. Fast tier decision — stays flat, gets honest colors (H2 fix included)

**No geometry in the fast tier** (its contract is textured flat cubes; the faithful tier owns geometry). Phase 2 adds to `_FLUID_FLAT` (preview.py:340):
- `minecraft:chest`: (181, 140, 82) — matches the faithful wooden box
- `minecraft:trapped_chest`: (170, 110, 75), `minecraft:ender_chest`: (60, 55, 70), copper family: (200, 120, 70)
- 16 `<color>_banner` / `<color>_wall_banner`: the vanilla dye RGBs

Signs need nothing (already textured flat cubes via the `all` texture var).

**H2 code change:** the faithful tier's "intentional approximation, no warning" behavior comes from its `_FLUID_RGBA` early return (preview_faithful.py:617–619), which fires *before* `fallback_blocks.add` — the fast tier has no such path: `_build_face_textures` (preview.py:546–561) unconditionally runs `fallback_blocks.add(name)` whenever a face texture is missing, and today `minecraft:water` **is** in fast-tier `fallback_blocks` despite being in `_FLUID_FLAT`. Phase 2 must add an explicit skip:
```python
if img is None:
    if name not in _FLUID_FLAT:
        # _FLUID_FLAT entries are intentional approximations
        # (flat blue water / orange lava, flat chest & banner colors) —
        # not missing-asset warnings.
        fallback_blocks.add(name)
    img = Image.new("RGB", (16, 16), _fallback_color(name))
```
**Behavior change (called out):** after this, `minecraft:water` and `minecraft:lava` will **stop** appearing in fast-tier `fallback_blocks`. Any consumer of `info["fallback_blocks"]` will see them disappear. Intended semantics — intentional approximations are not warnings — but a visible `info` output change; note it in the merge commit body.

Trusted tier: **out of scope** — it already draws rotation arrows for sign/banner `rotation`; it's the untextured truth tier by design.

## 8. Scope

**In:** `chest`, `trapped_chest`, `ender_chest`, all 8 copper-chest variants, all 32 banner blocks (16 colors × standing/wall), `_DEFAULT_PROPS` sign fix, `assets.py` entity-texture prefix, fast-tier flat colors + `fallback_blocks` skip.
**Explicitly out:** double chests (`type=left/right` renders as single — current behavior, noted), shulker boxes, Christmas chest textures (date-gated), banner **patterns** (block-entity NBT, stated limitation), sign **text** (vanilla renders text separately; out of scope), bed heads / skulls / other entity blocks.

## 9. Regression test plan (`tests/test_preview_faithful.py`, `test_preview.py`)

Real-asset tests use the existing `needs_real_assets` marker; synthetic tests use the `assets_root`/`tex_cache` fixtures. New tests:

1. `test_chest_not_fallback` — `minecraft:chest` (bare + `[facing=east]`) → `is_fallback False`, quads ≥ 15 (body 6 + lid 6 + latch ≥ 5), all textures RGB/RGBA (not flat magenta).
2. `test_chest_lid_above_body` — lid quads all y ≥ 0.62, body quads all y ≤ 0.63; lid min-y ≈ 10/16, body max-y ≈ 10/16.
3. `test_chest_facing_rotates_latch` — for each facing in {north,east,south,west}: latch-quad centroid lies on the facing side (e.g. east → mean x > 0.75). The direction-trust test.
4. `test_chest_textures_per_variant` — trapped/ender/copper chests → not fallback; optionally assert mean hue differs between normal and trapped crops.
5. `test_chest_missing_entity_texture_falls_back` — synthetic `assets_root` without `textures/entity/` → chest → wooden box (`is_fallback False`, 6 quads), trapped_chest → magenta fallback (`is_fallback True`). **Plus `assets_root=None`** (hook skipped by guard) → same expected outcomes.
6. `test_banner_not_fallback` — `minecraft:red_banner`, `minecraft:white_wall_banner[facing=east]` → not fallback, quads ≥ 10.
7. `test_banner_cloth_tint` — red banner cloth front crop red-dominant (r > g, r > b); white banner cloth near-white.
8. `test_banner_standing_rotation` — `rotation=0` cloth front normal ≈ +Z; `rotation=4` → west (−X after snap); `rotation=8` → north. Snapped normals + corner centroids.
9. `test_wall_banner_facing` — for each facing: cloth centroid on the wall side opposite the facing; cloth front normal == facing direction.
10. `test_sign_bare_resolves` — `minecraft:oak_sign`, `minecraft:oak_hanging_sign` (bare) → not fallback (pins the `_DEFAULT_PROPS` fix).
11. `test_sign_board_faces_facing` — `oak_wall_sign[facing=east]` → board front-face normal ≈ +X.
12. Fast tier (revised per H2): `test_fast_chest_flat_color` — chest face color == (181,140,82) AND chest NOT in `fallback_blocks`; `test_fast_banner_flat_color` — red_banner == dye red and NOT in `fallback_blocks`; `test_fast_fluid_no_warning` — water/lava NOT in `fallback_blocks` (pins the §7 behavior change).
13. `test_rot_y_degrees_matches_rot_y` — `_rot_y_degrees(p, d)` ≡ `_rot_y` applied d/90 times at d ∈ {0,90,180,270} for sample points (synthetic, no assets needed).
14. Existing suite: full 390 green (run `pytest` before/after).

## 10. Risks / open questions

- **Latch geometry is best-effort** (2×4×1 at x 7..9, y 11..15, z 0..1) — tiny, low visual risk, flagged as approximation.
- **Existing user caches lack entity textures** until cache deletion (`fetch` idempotency, §5) — graceful fallback covers it; consider a version-stamped cache or an `info` warning (open question for phase 2).
- **Double chests** render as two adjacent singles (current behavior preserved); `normal_left/right.png` not used — out of scope.
- **Dye RGB values** are the long-stable vanilla palette; if any look off in renders, adjust from the wool block textures in-cache.
- **Fast-tier `info` behavior change** (§7): water/lava leave `fallback_blocks`. Flag in the merge commit body.
- No AI/tool attribution anywhere git-facing (standing rule).

## 11. Direction-trust guarantee (extended)

Every oriented approximation gets a per-facing test (chest §9.3, standing banner §9.8, wall banner §9.9, sign §9.11) asserting the textured front / latch / cloth centroid lies on the expected side for **every** legal prop value — the same centroid/normal technique the existing stair-orientation tests use. Canonical-then-rotate construction (painted-on UVs, `_rot_y`/`_rot_y_degrees` with the documented clockwise-from-above convention) keeps the implementation in the same verified orientation model as the rest of the renderer. Test 13 pins the `_rot_y_degrees` ≡ `_rot_y` convention at 90° multiples.

## 12. Work order (phase 2, blocking steps in order)

1. Branch `acc/block-entities` from main @ ab39e88.
2. Asset pipeline: `assets.py` `_CLIENT_PREFIXES` entity prefix; document the cache-deletion idempotency caveat for users.
3. Faithful tier: `_entity_box_quads`, `_rot_y_degrees`, `_chest_quads`, `_banner_quads`, `_try_entity_quads` + the `resolve_block_quads` hook (before `_FLUID_RGBA`; preserve the fluid-height gap's `top_h` name-keying).
4. `_DEFAULT_PROPS` sign fix (preview.py) — includes the §4 re-audit note in a code comment.
5. Fast tier: `_FLUID_FLAT` additions + the `fallback_blocks` skip (§7).
6. Regression tests §9.1–13; full 390+ suite green.
7. **⛔ BLOCKING — pre-merge visual gate (M8).** The per-facing tests pin *orientation*, not *texture-region correctness*: the chest UV table (§2), banner regions (§3), and latch geometry were pixel-verified from the actual PNGs, but `textures/entity/` was never extracted to the asset cache — so they are the highest-risk unverifiable content in this plan. Before merge: render the approximations in the faithful tier (chest front/side/top incl. latch, banner front/back incl. a tinted color, all 4 facings) and eyeball them against in-game screenshots. If regions look off, adjust from the actual PNGs and re-verify; do not merge on green tests alone. Needs Luki (server access for reference screenshots).
8. Merge (position: third, after fluid-height → biome-tint); merge commit body notes the fast-tier `fallback_blocks` behavior change (water/lava) and the corrected `_DEFAULT_PROPS` reasoning.
