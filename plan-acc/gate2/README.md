# Visual gate — gap 2: smooth lighting / ambient occlusion

Branch: `acc/smooth-lighting` (commit with the AO implementation).
Scene built from `~/workspace/mcbuilder/plan-acc/gate2/ao-corner.nbt`
(structure NBT, DataVersion 4903 = MC 26.2).

## Scene layout (`ao-corner.nbt`)

All coordinates in block units, y up:

| Region | Coords | Blocks |
|---|---|---|
| Floor | x 0–10, z 0–4, y 0 | `minecraft:stone` |
| North wall | x 0–10, z 0, y 1–3 | `minecraft:stone` |
| West wall | x 0, z 1–4, y 1–3 | `minecraft:stone` |
| Leaves cube | x 4–5, z 2–3, y 1–2 | `minecraft:oak_leaves` (2×2×2) |
| Glass cube | x 7–8, z 2–3, y 1–2 | `minecraft:glass` (2×2×2) |

The north + west walls + floor form the **inside corner / crevice** case.
The leaves and glass cubes are the **occlusion-classification** cases.

## Renders

- `ao-on/iso.png`, `ao-on/top.png` — faithful tier **with** smooth lighting
  (branch `acc/smooth-lighting`).
- `ao-off/iso.png`, `ao-off/top.png` — same scene from `main @ ab39e88`
  (**no** AO), for before/after comparison.

## What to compare on shulkr.com's NBT viewer

1. Upload `ao-corner.nbt` to shulkr.com's NBT viewer (or open the
   structure in a vanilla client with smooth lighting ON).
2. **Inside corner (back of the scene):** the floor and wall faces
   meeting at the corner must show a smooth dark gradient into the
   corner. Compare `ao-off/top.png` (uniformly lit — wrong) vs
   `ao-on/top.png` (darkened corner). On shulkr/vanilla the corner
   should read as a soft shadow, deepest exactly at the corner.
3. **Leaves cube (center):** vanilla treats leaves as opaque for AO —
   the stone floor around/under the leaves must be visibly darkened,
   about as dark as the floor next to the stone walls. In
   `ao-on/top.png` the leaves sit in a dark patch; in `ao-off/top.png`
   they don't.
4. **Glass cube (right):** glass must NOT cast AO — the floor around the
   glass stays at full brightness, clearly brighter than around the
   leaves. (Same in both renders; this pins the classifier, not the
   brightness curve.)
5. **Iso view:** the same three checks from the `iso` angle — corner
   gradient at the back, dark pool under the leaves, clean floor under
   the glass.

## Known approximations (judge plausibility, not exact values)

- The brightness ramp `(0.4, 0.6, 0.8, 1.0)` for AO levels 0–3 is a
  vanilla-derived approximation (0.4 floor corroborated, linear ramp
  assumed) — expect the *shape* of the gradient to match vanilla, not
  the exact pixel values.
- Partial blocks (stairs/slabs) don't *cast* AO in this implementation
  (documented v0 gap) — none are in this scene.
- The leaves render **untinted** here: gap-1 (biome tint) is not merged
  yet. Tint × AO composition is covered by unit test
  `test_ao_tinted_leaves_composition`, not by these images.
- Fluids receive AO in this implementation (vanilla skips it) — no
  fluids in this scene.
