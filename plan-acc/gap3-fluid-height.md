# Phase 1 Plan — Fluid surface height (#3) — faithful renderer

## 1. Verified vanilla height value (with sources)

**Value: `H = 8/9 ≈ 0.8888889`** for still fluid with no same-fluid above.

Two independent sources confirm the exact constant:

1. **[minecraft_clone water rendering research](https://github.com/colonel-sandvich/minecraft_clone/blob/HEAD/docs/water_translucency/minecraft_water_rendering_research.md)** — based on the *official Minecraft Java 1.21.4 client jar decompiled with CFR, Yarn mappings* (i.e. measured from the real client, not a guess): *"MAX_FLUID_HEIGHT = 0.8888889, exactly 8.0 / 9.0"*; *"A fluid cell with same fluid directly above reports height 1.0"*; *"Otherwise its own height is amount / 9.0"* (a source block has amount 8 → 8/9).
2. **[minecraft_clone water flow rendering research](https://github.com/colonel-sandvich/minecraft_clone/blob/HEAD/docs/water_translucency/water_flow_rendering_research.md)** — same provenance: *"Vanilla uses a maximum visible top height around 8/9 for fluid without same-fluid above."*

**Lava:** no lava-specific "8/9" quote was found in any source, but the vanilla client runs **both fluids through the same fluid renderer** (`LiquidRenderer`/`FluidRenderer` — the height formula operates on `FluidState`, fluid-agnostically). The research doc's height rule is stated for fluid generally, and the second source says "for fluid" without a water-only qualifier. **Decision: apply H = 8/9 to both `minecraft:water` and `minecraft:lava`.** This is the most defensible value — the alternative (lava at 1.0) would contradict the shared-renderer architecture.

**Side faces (honesty note):** vanilla clips side faces at the corner-averaged surface heights too (roughly 0..8/9 for a lone still cell), *not* full-height. We deliberately keep sides full-height (see §4) as a documented approximation — it requires neighbor context the renderer's per-palette-entry quad cache doesn't have.

## 2. Precise change locations

All in `src/mcbuilder/preview_faithful.py`:

1. **New constant** near `_FLUID_RGBA` (line 581):
   ```python
   #: Vanilla fluid surface height for a still fluid cell with no same
   #: fluid above: exactly 8/9 (verified against the Java 1.21.4 client).
   _FLUID_SURFACE_HEIGHT = 8.0 / 9.0
   ```

2. **`_fluid_cube_quads(rgba)` (line 591)** — currently `f, t = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)` for all six faces. Change to per-face bounds:
   ```python
   def _fluid_cube_quads(rgba, top_height: float = 1.0):
       r, g, b, a = rgba
       quads = []
       for face_name in _FACE_NAMES:
           t = (1.0, top_height if face_name == "up" else 1.0, 1.0)
           corners = _face_base_corners(face_name, (0.0, 0.0, 0.0), t)
           ...
   ```
   `_face_base_corners` (line 398) builds corners from `f`/`t` directly, so passing `t = (1.0, H, 1.0)` for `"up"` lowers exactly the four top corners. `_order_corners_uv` (line 412) works on any corners — unchanged. Shading (`_SHADES[n]`) is per normal — unchanged.

3. **Caller `resolve_block_quads` (lines 610–619)** — currently:
   ```python
   if name in _FLUID_RGBA:
       return _fluid_cube_quads(_FLUID_RGBA[name]), False
   ```
   Change to pass `H` for fluids only, keeping the chest entry at 1.0 (chest is in `_FLUID_RGBA` but is a wooden box, **not** a fluid):
   ```python
   if name in _FLUID_RGBA:
       top_h = _FLUID_SURFACE_HEIGHT if name in (
           "minecraft:water", "minecraft:lava") else 1.0
       return _fluid_cube_quads(_FLUID_RGBA[name], top_height=top_h), False
   ```
   The `top_height` default of `1.0` keeps the chest behavior byte-identical and makes the signature self-documenting.

4. **UV handling:** no change required. The top face's "texture" is a flat 16×16 RGBA color (no texture sampling), so the lowered quad trivially spans the same color. Side faces keep full 0..1 geometry and their UV mapping is untouched.

5. **Translucency composition:** no interaction. `_draw_textured_quad` warps the RGBA image across whatever quad it's given and combines the polygon mask with texture alpha (`eff = poly * alpha`). Lowered geometry only shrinks the projected quad; the RGBA branch, shading (`_shade_image` shades RGB only, alpha preserved), and painter's-algorithm depth sorting are all unaffected. State in the code comment.

6. **No other files change.** `_render_view` needs nothing: framing uses whole-block crop bounds; back-face culling uses normals (unchanged); fluid quads carry no rotations.

## 3. Fast tier (`preview.py`) — scoped OUT

Justification: the fast tier is deliberately approximate — `_FLUID_FLAT` (preview.py lines 340–351) maps water/lava to opaque flat colors drawn on **full-cube** faces by the generic `_FACES` loop in `_render_view` (lines ~525–540), with no translucency and no per-block geometry special-casing. Lowering the fluid top there would require geometric offsets in the shared cube path (all blocks flow through the same offsets list), i.e. higher regression risk for a tier whose contract is "fast, approximate". The fidelity gap was filed against the faithful renderer, which is the direction-truthful tier where shape accuracy matters. Optionally revisit as a separate issue; do not bundle.

## 4. Edge cases — decisions

| Case | Decision |
|---|---|
| Side faces | Keep full 0..1 (approximation; vanilla clips at surface height — flagged as possible later refinement, not this phase). |
| Down face | Unchanged at y=0. |
| Chest | Explicitly excluded (keyed on fluid names, not the whole `_FLUID_RGBA` dict). |
| Same fluid above (vanilla reports 1.0) | **Not modeled.** `resolve_block_quads` is per-block with no neighbor context; neighbor-aware heights would break the per-palette-entry quad cache. Uniform H=8/9 for every fluid cell. Water columns will read slightly terraced — acceptable, documented. |
| Flowing vs still (`minecraft:water[level=1..7]`) | **Still-only scope this phase:** H applies uniformly regardless of `level`. Rationale: vanilla's flowing heights come from per-corner neighbor averaging; a single per-block stepped height would not be vanilla-accurate anyway, and the common build case (pools, rivers at rest, decorative water) is level 0. The fluid path currently ignores props entirely — threading `level` through is a future refinement (map `level` → `max(amount,…)/9` without corner averaging). Document the scope in the constant's comment. |
| Vanilla 0.001 top-vertex inset (z-fighting guard) | Not needed — no coplanar surfaces here (lowered top at 8/9 sits strictly below any full cube at y≥1.0). |

## 5. Regression test plan (`tests/test_preview_faithful.py`)

1. **Water top face:** `resolve_block_quads("minecraft:water", None, {})` → not fallback; the quad with normal `(0,1,0)` has all four y-coords `≈ 8/9` (`pytest.approx`) and max y `< 1.0`.
2. **Water sides unchanged:** the four side quads still span y ∈ `[0.0, 1.0]` exactly (min 0.0, max 1.0); down quad at y=0.
3. **Lava top face:** same assertions as (1) for `"minecraft:lava"`.
4. **Chest regression:** `"minecraft:chest"` top face y == 1.0 exactly (no lowering leaked through `_FLUID_RGBA`).
5. **Level-carrying canonical:** `"minecraft:water[level=1]"` renders (not fallback), top y == 8/9 — documents still-only scope.
6. **Alpha preserved:** top quad's image mode is `RGBA`, alpha == 150 (water) / 210 (lava) — guards the RGBA composition path in `_draw_textured_quad`.
7. **Render smoke:** tiny grid containing one water block → `render(...)` for one view writes a PNG without exception (follow the existing smoke-test pattern in the file).
8. **Determinism:** two consecutive `resolve_block_quads` calls produce identical quad coordinates (cache model untouched).

All 390 existing tests must stay green — note no existing test currently references fluids by name (grep for "fluid" in `tests/` returns nothing), so these are net-new tests.

## 6. Risks / open questions

- **Float exactness:** `8.0/9.0` is not binary-exact — tests must use `pytest.approx`, never `==`.
- **Stacked water visual:** vertical water columns get slightly terraced tops (each cell at 8/9 instead of the interior cells at 1.0) — a known, accepted approximation; proper fix needs neighbor-aware corner heights and would break the per-palette quad cache.
- **Side-face fidelity:** vanilla clips sides at the surface height; we keep them full-height. If Luki eyeballs it and complains, the follow-up is per-corner side heights — but that also needs neighbor context, so it belongs to a larger neighbor-aware rendering pass, not this gap.
- **Implementation (phase 2)** goes on branch `acc/fluid-height`; no AI/tool attribution in code comments or commits (standing rule).

## 7. Direction-trust guarantees — untouched

The change moves only the y-coordinate of the `"up"` face's four corners inside `_fluid_cube_quads`, a path that **bypasses the entire orientation pipeline** (no blockstate x/y rotation, no element rotation, no `_UV_AXES`/`uvlock` logic, no `_order_corners_uv` semantic change). Stair/wall/lantern/trapdoor rotation and facing conventions, the x-then-y rotation order, and the painted-on UV model are all unaffected.
