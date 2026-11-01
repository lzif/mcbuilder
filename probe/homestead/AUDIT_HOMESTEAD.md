# mcbuilder probe: riverside homestead (full survival base)

**Date:** 2026-11-01 · **Build:** `probe/homestead/homestead.py` (~700 lines)
**Result:** 35,052 blocks, 188 types, 78×36×63 — `check` 0 errors /
0 warnings. Three iterations (run-001 → run-003).

Contents: two-story Tudor house (stone ground floor, jettied timber
upper floor, cross gable, 2 dormers, exterior chimney + campfire), barn
+ lean-to forge + ridge cupola + hay hoist, watchtower on the hill
(crenellated parapet, turret roof), farm with 2 plots + water channel +
scarecrow, animal pen + shelter, roofed well in a plaza, a stream with an
arched bridge + dock, a palisade with a gate arch, an orchard + beehives,
a woodshed, trees, and patchy meadows.

Renders: `renders/` (final, faithful). `renders/v1_az225_el030.png` is
the first iteration, for comparison. Close-ups come from
`tools/focus.py` (§C2).

---

## A. How good is it, honestly

**Strong points:** the main house. Once you zoom in (see
`closeup_house_barn_*.png`) it reads clearly as a "Tudor cottage": the
stone/timber/roof bands are separated, the jetty + corbels cast a shadow
line, there's a cross gable over the porch, wooden bargeboards on the
gable ends, flower boxes, shutters, lanterns flanking the door, and a
chimney as the vertical accent. The tower's silhouette is also strong.
Zones are labelled by function and connected by paths, and the stream +
bridge tie the composition together.

**Weak points** (these are *my* weaknesses as an agent, not the tool's):

1. **Composition and density.** I sized the plate first (78×63) and then
   filled it with zones, so the buildings end up small and there's a lot
   of empty grass. A real diorama builder works the other way round:
   tight around the focal point, with the plate following the content.
   I had no "feel" for scale until the first render, and in a
   full-diorama render at this size, details are only a few pixels.
2. **Terrain.** The hill reads as concentric terraces (a contour map),
   not a natural slope. I only know how to make a heightmap with
   1-block steps. Smoothing with slabs/stairs, stone outcrops, and
   eroded edges are all missing. This is the weakest part of the build.
3. **Proportion and spacing between buildings.** The house, chimney and
   barn are packed together with almost no gap. I put down footprint
   coordinates without thinking about "breathing room" between masses.
4. **Repetition.** Shutters on every window, a lantern post every 6
   blocks, orchard trees that were perfect clones (fixed in iteration
   3). My instinct is to "apply the rule evenly", while good builders
   *vary* the rhythm (accent points, asymmetry).
5. **Roofs.** Dormers were broken in the first attempt (the dormer roof
   blended into the main roof); now they read as dormers, but their
   backs make bumps on the ridge. The barn roof is still a large slope
   of a single material, and a single row of spruce stairs isn't enough
   to break it up.
6. **Interior.** It exists (kitchen, dining table, beds, library,
   forge), but it's never visible in any preview, so it got the least
   iteration.

**Style "rules" I followed mechanically** (from `docs/build-patterns.md`)
work for houses. What's **missing** from the guide, and what I had to
guess at:

- **Composition/scale:** how big a building should be relative to the
  plot, how much distance between masses, and how to pick a focal point.
  The guide only says "orbit a terrain feature".
- **Terrain shaping:** no techniques at all (smoothing slopes,
  outcrops, banks, "where to put rocks").
- **Tree/foliage design:** no guidance on custom tree shapes (trunk
  branching, irregular canopy, varied size). The trees I made are still
  "lollipops".
- **Roof complexity beyond gables:** dormers, hip roofs, valleys, and
  roof corners (stair `shape=outer_*` is unclear to me, so I used full
  blocks at the hip roof corners).
- **Rhythm variation:** the guide says "repeat identical fixtures at
  regular intervals". That's right for lighting, but taken literally it
  makes everything look stamped.
- **Palette per biome/theme:** colour pairings I can trust. For example,
  `white_terracotta` turned out pinkish, not white, and I only found out
  after rendering.

---

## B. What the iterations proved (the loop works)

| Iteration | Problem I saw in the render | Fix |
|---|---|---|
| 1→2 | grass covered in random speckles (white noise) | value noise (`vnoise`): coarse dirt/moss/flowers in **patches** |
| 1→2 | plaster has pink patches | dropped `white_terracotta` |
| 1→2 | upper-floor flower boxes floating | leaves now sit on a top-half trapdoor ledge |
| 1→2 | flat black roof | wooden bargeboards + deepslate brick eave course (`retrim`), 2 dormers |
| 1→2 | long, plain barn roof | spruce band + ridge cupola |
| 1→2 | hill made of perfect rings | noise on the hill radius (still terraced, see A2) |
| 1→2 | empty zones | orchard + beehives, woodshed |
| 2 | dormer roof blended into the main roof | dormer rewritten: 3-tall front wall, wooden verge |
| 2 | X-brace in a 3-tall panel → blocky blob | swapped for close studding (mid-rail) |
| 2→3 | trees look white/frosty | **renderer bug**, fixed (see C1) |
| 2→3 | orchard trees are clones | random trunk/canopy/offset per tree |

---

## C. Tool findings (beyond the underwater probe)

### C1. FIXED: faithful renderer culled faces behind leaves
`_quad_culled_by_neighbor` used the AO occlusion grid, where leaves =
occluding. So faces between neighbouring leaves were discarded, the
holes in the leaf texture showed the background, and every canopy looked
hollow/white. Vanilla (fancy graphics) leaves are `noOcclusion`: they
never cull neighbouring faces. Fix in `preview_faithful.py`: leaves still
occlude for AO, but not for culling. Test:
`test_leaves_never_cull_neighbor_faces`.

### C2. No crop/zoom view, so details of large builds are unreadable
At 78×63, one block is about 20px in the full render. I wrote
`tools/focus.py` (copy a sub-box → new Build → render).
**Suggestion:** a view token like `focus:x0,z0,x1,z1` or
`--focus x0,y0,z0:x1,y1,z1` that crops/frames the camera.

### C3. `BUILD.set()` does not accept a material spec
`box/walls/cylinder/...` accept weighted lists or callables, but `set`
throws `ValueError: malformed block string`. I hit this twice and had to
write a `put()` wrapper with `resolve_material`. It's inconsistent and
surprising.

### C4. No value/patch noise
Coordinate-hash noise = per-cell speckle. I wrote `vnoise()` myself
(smooth value noise). This should be built in as a material spec, e.g.
`mb.noise.patches({...}, scale=5)`.

### C5. No helpers for: hip roof, dormer, roof retrim, terrain heightmap
I wrote `hip_roof`, `dormer`, `retrim` (re-material verge/rows while
keeping facing) and `ground()` myself. `roof_gable` already returns a
Geometry, so `retrim` is easy, but every agent will rewrite it.
**Suggestion:** `roof_hip`, a `trim=` option on `roof_gable` (verge/eave
material), and `mb.terrain.heightmap(fn, top=, fill=)`.

### C6. Trusted tier is unusable for large builds
Neon colours per block type (188 types) become camouflage
(`renders/trusted_tier_az135.png`). For direction checks it needs a mode
that only highlights directional blocks and greys out everything else.

### C7. Iteration speed
All tiers × 5 views for 35k blocks ≈ 110 s, faithful only ≈ 87 s,
`check` ≈ 2 s. That's fine, but per-region close-ups (C2) would be much
faster than rendering the whole diorama again.

### C8. Small items
- `leaf_litter` → magenta cube in faithful (orientation unknown).
- `palisade`/`railing`: no helper that follows terrain (a
  ground-following fence line). I wrote my own.
- No way to put **labels/annotations** in previews (zone names), which
  the guide itself recommends ("label every zone").
