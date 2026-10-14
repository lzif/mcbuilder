# Visual gate — gap4: block-entity approximations

**Status:** pre-merge gate (M8). The per-facing tests pin *orientation*, not
*texture-region correctness* — eyeball these renders against shulkr.com's
NBT viewer (close enough to in-game per Luki's call) before merging
`acc/block-entities`.

## Materials

- `gate4-block-entities.nbt` — the test structure (DataVersion from the
  26.2 cache). Upload to shulkr.com's NBT viewer.
- `renders/*.png` — faithful-tier renders from this branch (presentation
  mode, 2048px longest side):
  - `az045_el025.png`, `az135_el025.png`, `az225_el025.png`,
    `az315_el025.png` — 4 orbit angles, 25° elevation
  - `az000_el010.png`, `az090_el010.png` — low front/side views
  - `top.png` — top-down

## Layout (all at y=1 on a stone slab)

| Row (z) | x=0 → … | Contents |
|---|---|---|
| z=1 | 0–11 | chests: `facing=north/east/south/west`, then `trapped`, `ender`, `copper`, `exposed_copper`, `weathered_copper`, `oxidized_copper`, `waxed_copper`, `waxed_oxidized_copper` |
| z=4 | 0–7 | standing banners: `red[rotation=0/4/8]`, `blue[0]`, `lime[2]`, `black[12]`, `white[0]`, `yellow[6]` |
| z=7 | 0–5 | wall banners: `white[facing=north/south/east/west]`, `red[north]`, `orange[east]` |
| z=10 | 0–4 | signs: `oak_sign[rotation=0]`, `oak_sign[rotation=8]`, `oak_wall_sign[facing=east]`, `oak_wall_sign[facing=north]`, `oak_hanging_sign` |

## What to screenshot on shulkr.com (match each against our render)

1. **Chest front** (eye-level, straight on): pick the `facing=south` chest
   (x=2, z=1) — latch must be centered on the lid's front face, metallic
   gray; lid band above body band. Compare with our `az000_el010.png`.
2. **Chest side + top**: orbit to see the lid/body split and the latch
   protruding ~1px. Compare with `az045_el025.png` / `top.png`.
3. **Chest variants**: trapped (near-identical to normal — only 28/4096
   texels differ in vanilla!), ender (dark + gold latch), copper family
   (teal/orange/oxidized). Compare with `az000_el010.png`.
4. **Banner front/back**: `red[rotation=0]` (x=0, z=4) — red cloth, wood
   pole + crossbar; back side shows the darker cloth-back tint.
   Compare with `az000_el010.png` and `az225_el025.png`.
5. **Banner rotations**: `rotation=4` cloth faces west, `rotation=8` faces
   north; diagonal ones (`lime[2]`, `yellow[6]`, `black[12]`) show the
   cloth at 45°/135°/270°. Compare with `top.png` (cloth angles).
6. **Wall banners**: `white[facing=east]` (x=2, z=7) — cloth hangs on the
   west side of its cell, front faces east. Compare with `az090_el010.png`.
7. **Signs**: standing sign board + post, wall sign board on its facing
   side, hanging sign with chains. Compare with `az045_el025.png`.

## Known approximations (do NOT flag as bugs)

- Single chests only (`type=left/right` double chests render as singles).
- Banner cloths have NO patterns — only the base dye color.
- Signs have no text. Pole/bar wood crops are approximate 2px slices.
- Latch is 2×4×1 px — tiny by design.
