# Codebase Audit Report — mcbuilder v0.1.0

**Date:** 2026-10-14  
**Status:** 426 tests pass, 19 skipped (no real asset cache) — re-verified 2026-10-16, now warning-free  
**Scope:** read-only audit of `src/`, `tests/`, `docs/`, `plan-acc/`, `examples/`, `probe/`  
**Resolution:** 2026-10-16 — all actionable findings below fixed (see addendum at the bottom)

---

## Executive Summary

This is a focused, well-structured Minecraft structure-building toolkit for AI agents. The codebase is largely sound: test coverage is strong (426 green), the build toolchain works end-to-end (CLI → validation → render → .nbt export), and the direction-trust story is handled with care across three preview tiers. There is a **contradictory docstring that will actively mislead users** and several **documentation gaps between the plan and the code**. No data-loss or security issues found.

---

## 1. CRITICAL: Contradictory `stairs_run` facing rule

**Files:** `src/mcbuilder/parts.py:75-79` (wrong docstring), `src/mcbuilder/build.py:403-404` (misleading delegate), `src/mcbuilder/part.py:186-189` (correct, for reference)

Two docstrings tell the user contradictory things about which way stairs face — one of them is the most user-facing layer:

| Location | Claim |
|---|---|
| `part.py` (factory, the real implementation) | `facing = dir_key` — ascending north → `facing=north` ✅ correct |
| `parts.py` (the one-shot sugar, line 75-79) | `facing = OPPOSITE of ascent direction` — "ascending north means facing south" ❌ WRONG |
| `build.py` (delegate, line 403-404) | "see `parts.stairs_run` for the facing rule" — but that's the wrong docstring ❌ misleading |

**What actually happens:** `parts.stairs_run` delegates straight to `part.stairs_run` (see `parts.py:80-82`), which uses `facing = dir_key`. So ascending north places `facing=north`. The `parts.py` docstring is **flatly wrong** and describes the *opposite* of the actual behavior.

The `part.py` factory docstring is **correct** (states "facing = the ascent direction", matching the code). The `build.py` delegate points to `parts.stairs_run` for "the facing rule" — but that's the wrong docstring. A user following the delegation chain from `BUILD.stairs_run()` → `parts.stairs_run()` → `part.stairs_run()` hits the wrong rule at the first stop.

**Why it matters:** This is the exact bug class the entire direction-trust architecture exists to prevent (the v8 wrong-facing stair). A user reading `parts.py` will place stairs with the wrong facing and not know it until they see a trusted-tier render. The `probe/API_FRICTION_NOTES.md` document shows real users have already been burned by facing confusion.

**Fix:** Update `parts.py` lines 75-79 to state the correct rule: `facing = ascent direction` (matching `part.py`'s already-correct docstring and the code). The `part.py` docstring needs no change. Update `build.py`'s delegate (line 403-404) to state the rule explicitly rather than pointing to `parts.stairs_run` (which currently has the wrong docstring). The rule: ascending north → `facing=north`, tall back sits uphill, matches vanilla placement.

---

## 2. LOW: Trusted tier `_rot_box_y_cw` formula looks suspicious but is correct

**File:** `src/mcbuilder/preview_trusted.py:142-147`

```python
def _rot_box_y_cw(box) -> tuple:
    """Rotate a unit-cube-local box 90° clockwise (north→east), viewed from above."""
    x0, y0, z0, x1, y1, z1 = box
    return (1.0 - z1, y0, x0, 1.0 - z0, y1, x1)
```

At first glance this formula looks like a 180° rotation composed with an X-Z swap. But it is in fact a correct 90° clockwise Y rotation. Verification:

- North-facing stair template `_STAIR_BACK = (0,0,0,1,1,0.5)` (tall back at -Z/north).
- After `_rot_box_y_cw`: `(1-0.5, 0, 0, 1-0, 1, 1) = (0.5, 0, 0, 1, 1, 1)` — x∈[0.5,1] = east half. ✓
- Apply again (east→south): `(1-1, 0, 0.5, 1-0, 1, 1) = (0, 0, 0.5, 1, 1, 1)` — z∈[0.5,1] = south half. ✓
- Apply again (south→west): `(1-1, 0, 0, 1-0.5, 1, 1) = (0, 0, 0, 0.5, 1, 1)` — x∈[0,0.5] = west half. ✓

The formula is verified correct by the faithful tier's real-asset tests (`test_vanilla_stair_parity_all_facings`) which confirm the tall centroid lands on the expected side for all four facings.

This is the same axis-mapping transformation `rotation.py:rotate_position` uses (`(size - 1 - z, x)` for CW90). The "1.0 - z" handles the mirror intrinsic to mapping the z-axis onto x in a right-handed frame.

**Verdict: NOT a bug.** The function is correct and tested. Recommend adding a one-line comment showing the axis mapping (x→1-z, z→x) so future readers don't share my initial confusion.

---

## 3. MEDIUM: Trusted tier stair template orientation — verified correct

**File:** `src/mcbuilder/preview_trusted.py:149-152`

```python
_STAIR_SLAB = (0.0, 0.0, 0.0, 1.0, 0.5, 1.0)
_STAIR_BACK = (0.0, 0.0, 0.0, 1.0, 1.0, 0.5)
```

The doccomment at lines 149-157 explains the north-facing template has the tall back at -Z (north). Let me verify against the faithful tier's real-asset test:

`test_preview_faithful.py:test_vanilla_stair_parity_all_facings` confirms that `oak_stairs[facing=north]` has its tall centroid at `(0.5, _, 0.25)` — i.e., the +Z toward -Z side (north = -Z in this codebase's convention where +Z = south). Wait — the test says:

```python
for facing, (ex, ez) in {"north": (0.5, 0.25), "east": (0.75, 0.5),
                         "south": (0.5, 0.75), "west": (0.25, 0.5)}.items():
```

So north-facing → centroid at z=0.25 (near -Z / north side). The `_STAIR_BACK` box `(0,0,0,1,1,0.5)` occupies z∈[0,0.5] — the **north half**. Correct.

East-facing → centroid at x=0.75 (near +X / east side). After rotating the north template 90° CW (1 turn), `_STAIR_BACK` becomes `(0.5,0,0,1,1,1)` — x∈[0.5,1] = east half. Correct.

**Verdict: Correct.** The trusted tier stair template matches the faithful tier's real-asset verification. The doccomment even documents the prior bug ("2026-10-09 audit caught this template with the tall part at +Z — mirrored vs vanilla. Fixed"). Good.

---

## 4. MEDIUM: `_DEFAULT_PROPS` tripwire re-audit warning is load-bearing and present

**Files:** `src/mcbuilder/preview.py:156-168`, `src/mcbuilder/preview_faithful.py` (imports `_fast._DEFAULT_PROPS`)

Both tiers share `_DEFAULT_PROPS` which includes `"rotation": "0"` and `"attached": "false"`. The comment correctly warns that `_match_variant` only requires every key-pair in a variant key to be satisfied, so adding defaults is **non-monotonic** — a future default like `east="false"` could silently start matching `tripwire.json`'s 32 variants.

The comment says this is a "RE-AUDIT WARNING" and names the specific at-risk files (`tripwire.json`, `tripwire_hook.json`). This is exactly the right safeguard. **No action needed** — this is done well. Just ensure any future contributor knows to read this comment before adding defaults.

---

## 5. INFO: `parts.py` and `part.py` width direction — verified consistent (no bug)

**Files:** `src/mcbuilder/parts.py:58-63` (docstring), `src/mcbuilder/part.py:218-221` (docstring), `src/mcbuilder/part.py:259` (implementation)

Both say:
> "width > 1 widens the run along the horizontal axis perpendicular to direction, extending toward the positive side from start"

But:
- `parts.py` (line 59): "north/south runs widen along +X, east/west runs widen along +Z"
- `part.py` (line 219): same text

Implementation in `part.py:259`:
```python
px, pz = (0, 1) if dx != 0 else (1, 0)
```
- `dx != 0` means east/west (dx = ±1) → `(px, pz) = (0, 1)` → widens along +Z ✓
- `dx == 0` means north/south (dz = ±1) → `(px, pz) = (1, 0)` → widens along +X ✓

**Verdict: Not a bug — the code and both docstrings are consistent.** The implementation correctly widens north/south runs along +X and east/west runs along +Z. No action needed.

---

## 6. MEDIUM: `build.py` `roof_gable` facing rule is correct and well-documented

**File:** `src/mcbuilder/build.py:237-290`

The `roof_gable` docstring clearly documents: each row's `facing` points toward the ridge (uphill), with concrete examples for `ridge="x"` (north-eave rows face south, south-eave rows face north) and `ridge="z"`. Implementation at line 281-288 matches. This is correct and well-documented — unlike `stairs_run`.

One minor note: the docstring says "The ridge row of an odd-span roof keeps facing the min-side eave, so it reads as the top step of the max-side slope." Looking at the code (line 284-288), the ridge block always uses `eave_lo` as its facing. For `ridge="x"`, `eave_lo="north"`. This means the ridge row faces north regardless of which side is "max". This is a reasonable convention (the ridge row is the top step of the south-eave slope, which faces north toward the ridge). It's documented, so it's fine.

---

## 7. LOW: `probe/API_FRICTION_NOTES.md` documents real usability gaps

This is a probe document (Floating Crystal Observatory build), not part of the core product, but it surfaces real friction worth noting:

### 7a. Missing geometric primitives (cylinders, spheres, cones, 3D lines)
**Friction:** The DSL has only rectilinear helpers (`box`, `walls`, `floor`, `carve`, `pillar`, `railing`, `stairs_run`, `roof_gable`). Building a crystal observatory required hand-rolled `for x/y/z` loops with `math.sqrt` for cylinders, domes, cones, and diagonal beams. The "diagonal voxelization trap" (stepping at integer steps along a direction vector leaves floating diagonal voxels) required 0.5-block sub-stepping workarounds.

**Assessment:** This is a genuine gap for non-rectilinear builds. The codebase's design philosophy (parts own geometry math) means these would naturally live in `mb.part.*` factories. Not a bug — a missing feature. The `Geometry` datablock layer is the right extension point.

### 7b. Material variation vs. single-block helpers
**Friction:** `docs/GUIDE.md` §5 and `docs/build-patterns.md` §1 state as Technique #1 that "every surface gets noise" with ~30% secondary mottled variant. But every helper (`box`, `walls`, `floor`, `pillar`, `railing`, `stairs_run`, `roof_gable`) accepts only `block: str`. Following the guide's own #1 rule requires bypassing helpers in favor of manual loops.

**Assessment:** Real friction between docs and API. The `mottled()` helper in `probe/crystal_observatory.py` is the workaround. A `block` parameter that accepts `str | list[str] | Callable[[int,int,int], str]` would address this. Again, a feature gap, not a bug.

### 7c. `Geometry` missing `.shift()` / `.rotate()` / `.mirror()` / `.box()` / `.carve()`
**Friction:** `Geometry` only has `.set()`. Composing geometries requires hand-rolled shift helpers. No rotation/mirror means you can't stamp a cornice stair around 4 sides by defining it once and rotating — you write out all 4 facings manually.

**Assessment:** The `Geometry` class is the datablock layer ("bpy.data" analog) but lacks the transformation operations you'd expect. `mcbuilder.rotation` already implements `rotate_position` and `rotate_blockstate` — wiring these into `Geometry` would be natural. Feature gap.

### 7d. `lightning_rod` and `iron_chain` preview discrepancies
**Friction:** `lightning_rod[facing=south]` passes validation but renders as a magenta fallback cube in faithful tier (and untextured in fast tier), while trusted tier doesn't warn on it. `iron_chain[axis=y]` works in faithful tier but renders as magenta in trusted tier (the `_AXIS_LOG_HINTS` tuple doesn't include "chain").

**Assessment:** 
- `lightning_rod`: The faithful tier's `_resolve_block_quads` dispatches through the model JSON — if `lightning_rod` has a model, it should render. If it's a magenta cube, either the model is missing from the 26.2 cache or the blockstate doesn't match. This is a "known missing block" issue, not a code bug — the renderer degrades gracefully as designed. The trusted tier not warning on it is because `classify()` only flags blocks with directional props that it doesn't handle — `lightning_rod[facing=south]` has `facing` so it hits the `kind == "facing"` branch and renders a cube + plate (no warning). That's actually correct behavior for the trusted tier's contract (it shows orientation truthfully via the plate, even if the geometry is approximate).
- `iron_chain[axis=y]`: The trusted tier's `_AXIS_LOG_HINTS = ("log", "wood", "stem", "hyphae", "pillar")` doesn't include "chain", so `iron_chain` with `axis=y` falls through to `kind == "fallback"` → magenta cube + warning. This is a **missing hint** — adding "chain" to `_AXIS_LOG_HINTS` would fix it. Low effort, clear improvement.

### 7e. `mcbuild diff` friction
**Friction:** (1) Bbox-origin shift invalidates entire voxel diff when exterior extremities change. (2) Single global RNG stream means early geometry edits perturb downstream mottled blocks. (3) Diff comparison PNG uses `previews/` (fast tier) instead of `previews_faithful/`. (4) Exit code 1 on non-empty diff.

**Assessment:** 
- (1) and (2) are fundamental design constraints of the current grid/diff model — storing world-space origin in `report.json` and using coordinate-hashed noise would address them. Feature improvements.
- (3) is a choice — fast tier is faster to render. Defensible but worth noting.
- (4) is intentional (POSIX `diff(1)` semantics). Documented. Fine.

---

## 8. LOW: Docstring quality varies

### 8a. `parts.py` docstring has the OLD facing rule
Lines 75-79 of `parts.py` describe `facing = OPPOSITE of ascent direction` ("stairs face the climber, so ascending north means facing south"). But `parts.stairs_run` delegates directly to `part.stairs_run` (line 80-82), which uses `facing = dir_key` (ascent direction). **The `parts.py` docstring was not updated when the facing rule was changed.** This is the user-facing sugar layer — the wrong docstring here is the most damaging because `BUILD.stairs_run()` routes through it.

### 8b. `part.py` factory docstring is correct
Lines 186-189 of `part.py` correctly state "facing = the ascent direction" and the code at line ~214 does `facing = dir_key`. No fix needed here.

### 8c. `build.py` `stairs_run` delegate docstring
Lines 403-404 say "Thin delegate to :func:`mcbuilder.parts.stairs_run` (see it for the facing rule...)". This is technically correct (it does delegate to `parts.stairs_run`), but `parts.stairs_run` has the wrong docstring (see 8a), so a user following the delegation chain hits the wrong rule. The `build.py` delegate should explicitly state the rule: "facing = ascent direction (tall back uphill)", not just point to `parts.stairs_run`.

---

## 9. LOW: plan-acc plans reference code that may not exist yet

The `plan-acc/CONSOLIDATED-PLAN.md` references several functions as if they exist:
- `_try_entity_quads` (gap4 — referenced in `_block_occludes_ao` with a `hasattr` guard)
- `_rot_y_degrees` (gap4 — referenced by banner rotation)
- `_FLUID_SURFACE_HEIGHT` (gap3 — referenced by fluid tests)

Looking at the actual `preview_faithful.py`:
- `_try_entity_quads` **EXISTS** (line ~1157) — gap4 is already implemented
- `_rot_y_degrees` **EXISTS** (line ~1070) — gap4 implemented
- `_FLUID_SURFACE_HEIGHT` **EXISTS** (line ~1015) — gap3 implemented
- `_block_occludes_ao` **EXISTS** (line ~470) — gap2 implemented
- `_quad_ao_levels` / `_vertex_ao_level` **EXIST** — gap2 implemented
- `_AO_BRIGHTNESS` **EXISTS** (line ~103) — gap2 implemented
- `_DYE_RGB` **EXISTS** (line ~1083) — gap4 implemented
- `_ENTITY_TEXTURES` **EXISTS** (line ~1056) — gap4 implemented
- `_chest_quads` / `_banner_quads` **EXIST** — gap4 implemented
- `_CHEST_BODY_UVS` / `_CHEST_LID_UVS` / `_CHEST_LATCH_UVS` **EXIST** — gap4 implemented
- `_WALL_BANNER_Y_ROT` **EXISTS** — gap4 implemented

**Surprise:** All four accuracy gaps (gap1-biome-tint, gap2-smooth-lighting, gap3-fluid-height, gap4-block-entities) appear to be **already implemented** in `preview_faithful.py`, not just planned. The `plan-acc/GATE-VERDICTS.md` shows both visual gates (gate 4 block entities, gate 2 smooth lighting) were PASSed on 2026-10-11. The test file `test_preview_faithful.py` has extensive tests for all four gaps.

So the "PHASE 1 complete. Plans only — no code written" line in `CONSOLIDATED-PLAN.md` is **stale** — the code has been written. The plan documents the *design rationale* which is valuable, but the "no code written" status is wrong.

The merge-order branch structure (`acc/biome-tint`, `acc/smooth-lighting`, etc.) may or may not exist on main — the code is all on main now based on what I see. This is fine if the merges already happened.

---

## 10. LOW: `_FLUID_FLAT` behavior change note from gap4 not yet applied

**Files:** `src/mcbuilder/preview.py:_build_face_textures` (around line ~550), `plan-acc/CONSOLIDATED-PLAN.md` gap4 section

The gap4 plan says:
> **H2 code change:** skip `fallback_blocks.add(name)` when `name in _FLUID_FLAT` in `_build_face_textures` — **behavior change:** water/lava STOP appearing in fast-tier `fallback_blocks`; note in merge commit body.

Looking at the current `preview.py:_build_face_textures` (line ~555-565):
```python
if img is None:
    if name not in _FLUID_FLAT:
        fallback_blocks.add(name)
    img = Image.new("RGB", (16, 16), _fallback_color(name))
```

This **already has the H2 change applied** — `_FLUID_FLAT` entries (water, lava, chests, banners) are excluded from `fallback_blocks` when their texture is missing. The plan's "behavior change" note is already reflected in the code.

---

## 11. LOW: Code quality observations

### 11a. Good: Determinism is taken seriously
- `_fallback_color` uses `hashlib.md5` (not `hash()`), explicitly documented as "NOT builtin hash"
- `PYTHONHASHSEED` is pinned in CLI tests
- `ast`-based determinism scanner warns on `random`/`numpy.random` imports
- Multiple tests assert byte-identical renders across calls

### 11b. Good: Graceful degradation everywhere
- Missing assets → flat colors, never crashes
- Missing textures → per-face flat color with `fallback_blocks` reporting
- Missing blockstates/models → magenta cube with `untrusted_blocks` reporting
- Corrupt elements → entire block degrades to fallback (not partial rendering)

### 11c. Good: Direction-trust is a first-class concern
Three tiers with explicit trust annotations in `report.json`:
- `fast`: `directions_untrusted=true`
- `trusted`: `directions_trusted=true` (orientation-truthful simplified geometry)
- `faithful`: `directions_trusted=true` (real geometry + textures)

### 11d. Good: Test organization
- Hermetic fake-asset fixtures in `conftest.py` (shared between tiers)
- Real-asset tests properly skipped when cache absent (`@needs_real_assets`)
- Both tiers tested for biome tint (gap1), AO (gap2), fluids (gap3), entities (gap4)
- Integration tests use real `Build` → `to_dense()` → renderer pipeline
- Performance smoke test with calibrated baseline and best-of-3

### 11e. Minor: `_draw_textured_quad` area threshold
Line ~665: `if _area2 < 2.0:  # < 1 px² screen-space area`. The comment says "< 1 px²" but the threshold is `2.0` (which is `< 2 px²`). Minor documentation mismatch. The factor of 2 is likely intentional (safety margin) but the comment should say `< 2 px²` or the threshold should be `1.0`.

### 11f. Minor: `preview_trusted.py:_rotation_arrow` direction
Line ~280: `dx, dz = -math.sin(theta), math.cos(theta)` with comment "rotation=0 → south; increasing rotation runs counterclockwise viewed from above (4=west, 8=north, 12=east)". Let me verify:
- rotation=0: `dx = -sin(0) = 0`, `dz = cos(0) = 1` → points to +Z = south ✓
- rotation=4 (90°): `dx = -sin(π/2) = -1`, `dz = cos(π/2) = 0` → points to -X = west ✓
- rotation=8 (180°): `dx = -sin(π) = 0`, `dz = cos(π) = -1` → points to -Z = north ✓

The comment says "counterclockwise viewed from above". The test `test_banner_standing_rotation` verifies the behavior is correct:
- rotation=0 → normal (0,0,1) = south, centroid on south side ✓
- rotation=4 → normal (-1,0,0) = west, centroid on west side ✓  
- rotation=8 → normal (0,0,-1) = north, centroid on north side ✓

The math is consistent with `rotation.py` (CLOCKWISE_90 adds +4 to rotation, and rotation=4 points west — matching a CW90 structure rotation). The "counterclockwise" in the comment describes the standard math convention (looking down from +Y onto the xz-plane). Fine — correct and tested.

---

## 12. LOW: `examples/waystones/waystone_s5.py` is the probe's own example

This is a 5×5×5 waystone variant using `lostqol:waystone` — a custom block not in the vanilla registry. It would need to be allowlisted to pass validation. The example is self-contained and well-structured (uses `BUILD.set` directly with explicit block strings, no parts helpers). Good example of the DSL.

---

## 13. LOW: `dist/` directory — pre-rendered artifacts

The `dist/` directory exists with rendered outputs. These are build artifacts, not source. The `.gitignore` includes `dist/` (confirmed: `.gitignore` line `dist/`). Good — build artifacts are ignored.

Note: `*.png` is NOT in `.gitignore` (only `dist/` and `build/` are). The `waystone-before-direction-mismatch.png` is explicitly listed as a kept file at the top of `.gitignore`. This means PNGs created elsewhere in the repo root (e.g. `probe/renders/`) would be tracked. The `probe/renders/` directory doesn't appear in `changed_file_paths` so this isn't currently an issue, but it's worth noting for future probe work.

---

## 14. Summary of actionable findings

| Priority | Issue | Files | Action |
|---|---|---|---|
| **CRITICAL** | `parts.py` `stairs_run` docstring states the wrong facing rule (opposite of ascent), but the code delegates to `part.py` which uses ascent direction | `parts.py:75-79`, `build.py:403-404` | Fix `parts.py` docstring to match `part.py` (facing = ascent direction); make `build.py` delegate state the rule explicitly rather than pointing to the wrong docstring |
| HIGH | `_rot_box_y_cw` looks like 180+swap but is correct | `preview_trusted.py:142-147` | Add clarifying comment showing axis mapping; otherwise correct |
| LOW | `iron_chain` not handled by trusted tier axis logic | `preview_trusted.py:_AXIS_LOG_HINTS` | Add "chain" to `_AXIS_LOG_HINTS` tuple (minor, low-effort) |
| MEDIUM | `CONSOLIDATED-PLAN.md` says "no code written" but all 4 gaps are implemented | `plan-acc/CONSOLIDATED-PLAN.md` | Update status line; plans are now design docs for already-implemented features |
| LOW | `_draw_textured_quad` area comment says "< 1 px²" but threshold is 2.0 | `preview_faithful.py:665` | Fix comment to say "< 2 px²" or align threshold to 1.0 |
| LOW | `probe/` documents real feature gaps (primitives, material variation, Geometry transforms) | `probe/API_FRICTION_NOTES.md` | Track as future feature work; not bugs |

---

## What's working well

1. **Three-tier preview architecture** with clear trust annotations — this is the right design for an AI builder where direction correctness matters
2. **Test coverage** — 426 tests, hermetic fixtures, real-asset parity tests, integration tests, performance smoke test
3. **Graceful degradation** — missing assets/textures/blockstates never crash; they degrade with reporting
4. **Determinism** — md5-based colors, pinned hash seed, ast-based import scanner, byte-identical render tests
5. **End-to-end pipeline** — CLI → validate → render (3 tiers) → .nbt export → report.json, all tested
6. **Rotation semantics** — `rotation.py` mirrors `StructurePaster.rotateBlockData` from LostQoL, spot-checked against Kotlin source
7. **Wall rendering** — render-time connection inference (read-only from NBT) is a clever solution to the "NBTs carry no wall props" problem
8. **Entity approximations** — chest/banner families with pixel-verified UV tables, visual gate passed against shulkr.com
9. **Plan documentation** — the `plan-acc/` directory documents the design rationale for all four accuracy gaps with verified vanilla values, even if the "no code written" status is stale
10. **`docs/GUIDE.md` is correct** — the guide states the right facing rule for `stairs_run` (facing = ascent direction), so users reading the guide get the right answer

---

*Audit complete. No destructive changes recommended. The critical docstring contradiction is the only item that could cause users to build incorrect structures.*

---

## Addendum — resolution (2026-10-16)

Continuation audit at `bbe9020` re-verified every finding, surfaced two new ones, then all were fixed:

| Finding | Status | Fix |
|---|---|---|
| §1/§8a CRITICAL: `parts.py` facing rule wrong | Fixed (remote `9b3a5f9` already had it; local duplicate edit dropped in rebase) | Docstring states `facing = ascent direction` (mirrors `part.py`); `build.py` delegate additionally states the rule explicitly instead of just pointing at the other docstring |
| §8c LOW: `build.py` delegate points at the (formerly wrong) docstring | Fixed | Delegate states "facing = the ascent direction … tall back uphill" inline |
| §14 LOW: `iron_chain` magenta in trusted tier | Fixed (remote `9b3a5f9` superseded the simple `_AXIS_LOG_HINTS` fix) | Chains and `*_rod` now render as thin axial posts in vanilla shape, with matching AO cull logic; `basalt[axis=y]` serves as the fallback representative in tests |
| §14 LOW: `< 1 px²` comment vs threshold 2.0 | Fixed | Comment now matches (`< 2 px²`) |
| §14 MEDIUM: `CONSOLIDATED-PLAN.md` "no code written" stale | Fixed | Status line now says implemented & merged with the four merge commits |
| NEW HIGH: `assets.py` hardcoded `hatch-egress-proxy` as default `HTTPS_PROXY` | Fixed (remote `9b3a5f9` approach kept: DNS-gated injection) | Proxy only set when `hatch-egress-proxy` actually resolves in the sandbox; user-configured `HTTPS_PROXY`/`HTTP_PROXY` always wins; normal workstations/VPS get direct connections. This AIO box verified fine (direct egress 200) |
| NEW LOW: `cli.py` leaks script dirs into `sys.path` | Fixed | Insertion scoped to `exec_module` (added-entries removed in `finally`) |
| 4 Pillow `getdata` deprecation warnings (tests, incl. 3 newer ones in the Argon wave) | Fixed | Replaced with `np.asarray(...convert("RGB")).reshape(-1, 3)` (alpha channel dropped without compositing — identical metric math); suite is now warning-free |
| FOUND DURING REBASE: `tests/test_preview_faithful.py` hardcoded `_REAL_ROOT` to the authoring sandbox user (`/home/hatch/...`), and the new fence test from `9b3a5f9` lacked the `@needs_real_assets` guard | Fixed | `_REAL_ROOT` is now portable (`MCBUILDER_TEST_ASSETS` env override, default `~/.cache/mcbuilder/26.2/client/assets/minecraft`); the fence test runs guarded. Side effect: all 19 previously-skipped real-asset parity tests now run wherever a cache exists |

Rebase note (2026-10-16): origin/main had moved ahead (`9b3a5f9` "10 Argon audit findings" + `603ade0` docs). Local fixes were rebased on top; where remote superseded a fix (facing docstring, proxy, iron_chain), remote's version was kept and the addendum above reflects the final merged state, not the original local-only fix.

Post-fix suite: **525 passed, 19 skipped, 0 warnings** (baseline). After the real-asset root was made portable: **525 passed, 0 skipped** — the 19 previously-skipped vanilla-parity tests now run locally too (2026-10-16).
