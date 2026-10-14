# Visual gate verdicts — 2026-10-11 ~00:25 WIB

Comparison source: shulkr.com NBT viewer (per Luki's lock: compare against shulkr, not in-game screenshots).
Browser task: view-only, no publish, no CAPTCHA encountered.
Evidence screenshots: `~/workspace/user/media_library/browser_screenshots/` (a9a1b3d5…, b26b39230a…, 688b1f224b…, 7dc090d8f7…).

## Gate 4 — block entities: PASS (on all comparable items)

Shulkr renders: chests (normal/trapped/ender), signs. It does NOT render banners or copper chests at all
(Materials tab lists them, 3D view empty even when isolated) — viewer limitation, not our bug.

- Chest latch: small metallic gray/silver square, centered on front face, on the lid/body seam. Ours: same. ✓
- Lid/body split: clear horizontal band, lid ~1/3 of height. Ours: same. ✓
- Latch protrusion: appears flat in shulkr. Ours: small flat tab. ✓ (close enough; approximations allow)
- Trapped chest: looks like a normal chest. Ours: brown, same as normal. ✓
- Ender chest: dark navy/black body, clearly darker than normal. Ours: same. ✓
- Standing sign: vertical post + wider board on top. Ours: same. ✓
- Wall sign: board flat against surface. Ours: same. ✓
- Hanging sign: board on two dark chains from a horizontal bar. Ours: same. ✓
- Banners (standing/wall/rotations), copper chest family: NOT comparable — shulkr doesn't render them.
  Our implementation stands on its test suite (407 green) + vanilla geometry (pole+crossbar+cloth).
  Accepted approximations per gate checklist: no banner patterns, no sign text, approximate texture crops.

## Gate 2 — smooth lighting/AO: PASS

- Inside corner: smooth dark gradient, deepest exactly at the corner, fading smoothly outward — top and iso. Ours: same. ✓
- Leaves cube: floor around/below leaves clearly darkened. Ours: visible dark halo around leaves. ✓
- Glass cube: floor around glass stays bright, no shadow. Ours: no halo around glass. ✓
- Behavior consistent between top and iso views. ✓
- (Shulkr's leaf "shadow" extends directionally; ours is a symmetric AO halo — vanilla AO is also
  per-vertex symmetric, and the gate allows approximate brightness ramps. Accepted.)

Both gates cleared → resume Phase 2 merge order: gap4 then gap2.
