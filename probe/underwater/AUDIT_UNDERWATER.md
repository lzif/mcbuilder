# mcbuilder probe: underwater research base (agent's-eye audit)

**Date:** 2026-11-01 · **Build:** `probe/underwater/underwater_base.py`
(≈190 lines; 10,074 cells incl. 1,744 explicit air; 53×14×53)
**Result:** `mcbuild check` 0 errors / 0 warnings; 527 tests pass.

Final renders: `renders/` (faithful tier). `renders/cutaway_iso.png` and
`renders/ocean_context_iso.png` were rendered with the throwaway scripts
in `tools/`, because the CLI can't produce those views yet (§B2, §B3).

What I built: a glass dome hub (r=9) with prismarine meridian ribs, an
east tube tunnel to an observation pod (r=6 dome, conduit), a north tube
to a moon-pool airlock room (a 3×3 water shaft through the floor), plus
a mottled seabed with kelp, seagrass, coral and sea pickles.

---

## Verdict

Yes, it's usable for an AI agent. The parts that helped most:
`check` runs in under a second, every helper returns its `Geometry` so
I can measure what I placed, material specs accept callables (that's
how I did the dome ribs as `fn(x,y,z)`), `rng("life")` gives me a
namespaced RNG, `sphere(dome=, hollow=)` exists, and
`render(tier="faithful")` is good enough to judge how the build looks.
The top view caught one of my bugs right away: the north tunnel ran
past the room.

For an **underwater** build specifically, though, I found one critical
problem and several "you can't see it until you're in-game" gaps:

---

## A. Fixed in this commit

### A1. CRITICAL: no export mode kept the interior dry *and* the ocean wet

- Default export: explicit `minecraft:air` is **not written**. On paste,
  ocean water stays inside the dome, so the base floods.
- `--include-air`: also writes every **unset** bbox cell as air. For
  this build that was 30,996 air cells against 1,744 intended, so the
  paste would leave a 53×14×53 dry hole in the ocean around the base.
- The docs implied the right behaviour existed ("carved air is
  distinguishable from untouched cells — that's what the exporter's
  `include_air` flag needs"), but the code didn't do it.

**Fix:** `mcbuild run --air {none,explicit,all}` and
`write_structure_nbt(include_air="explicit")`. `explicit` writes only
the cells you set to air, and unset cells stay structure-void. The old
`--include-air` / `True` still works as an alias for `all`. Covered by
tests; the GUIDE is updated. With `--air explicit` this build writes
exactly 1,744 air cells.

---

## B. Things I struggled with (recommended improvements, ordered by impact)

### B1. No airtightness / leak check, so the bug only shows up in-game
The first version had **16 air cells next to the open ocean**: the tube
ends overshot the room, and where the east tube meets the small pod
dome, the dome curved away from the top of the tube and left a gap.
`check` said OK, and no preview tier shows it. I found it only by
writing `tools/leak_check.py`, which flags air cells that share a face
with an unset (= ocean) cell.
**Suggestion:** an opt-in lint, e.g. `Build(enclosed_air=True)` or
`mcbuild check --leaks`, that reports leaking air cells with
coordinates. Same idea for "water-dependent block (kelp, seagrass,
coral fan) next to explicit air", which breaks or dies on paste.

### B2. No cutaway / section view, so I can't check the interior
The dome is mostly glass, but the props, tunnel walkways and the moon
pool still can't be read from outside. My workaround was to run the
script, `carve()` everything above y=4, and call `BUILD.render`
(`tools/cutaway.py`).
**Suggestion:** a view token like `cut_y5` / `section_x0` that clips
at render time without touching the grid.

### B3. No environment context in the preview
The build renders floating on a beige background, so I can't judge how
it "reads" underwater. Filling unset cells with water by hand
(`tools/cutaway.py ocean`) works, but it exposed a renderer bug: water
draws faces against kelp, seagrass and waterlogged cells, which are
water themselves. Kelp columns show up as glass-like pillars, and the
whole volume looks like stacked aquarium tanks.
**Suggestion:** `--env ocean:y=12` for preview-only water, and cull
water faces against kelp, seagrass, bubble columns and any
`waterlogged=true` neighbour.

### B4. `cylinder` / `cone` are vertical only
Every underwater tunnel is a horizontal tube. I wrote my own `tube()`
(about 25 lines, with interior air). `Geometry.rotate` only turns about
Y, so I couldn't lay a cylinder on its side either.
**Suggestion:** `cylinder(axis="x"|"y"|"z")`, plus a
`hollow=True, fill="minecraft:air"` option that returns shell and
interior together. Shell plus an air interior is the core pattern for
any enclosed build.

### B5. Air-pocket workflow depends on ordering
The correct order is shell → interior air → floor → props, and it's
easy to get wrong because air overwrites the doorway/shell where two
volumes meet (227–303 overwritten placements per run). A helper like
`BUILD.hollow(geo, air=True)` or `sphere(..., interior="minecraft:air")`
would make the intent explicit.

### B6. Material noise is white noise
The coordinate-hash palette (`[("sand",6),("gravel",2),...]`) turns
into a speckled checkerboard (see `renders/top.png`). Real builders use
patches (clusters).
**Suggestion:** `mb.noise.patches(palette, scale=3)` (value or Perlin
noise) as a material spec.

### B7. No waterlogging help or lint
Outside stairs and slabs in water should be `waterlogged=true`, or they
leave air gaps. Inside the air pocket they must be `false`. Coral fans
must be `waterlogged=true`, or they die. All of this passes `check`
silently.
**Suggestion:** a context-aware warning: a waterloggable block whose
neighbours are unset/water but is not waterlogged (and the reverse).

### B8. Small items
- `minecraft:conduit` → magenta fallback cube in faithful, flat colour in fast.
- `mcbuild diff` takes a run **id** (`run-001`), not a path
  (`dist/run-001` → "invalid run id"). Tab-completion produces paths,
  so it should accept both.
- `diff` still exits 1 when there are differences (POSIX style), so
  agent tool wrappers report it as a failed command. A `--exit-zero`
  flag would help.
- Material specs (weighted lists and callables) are a great feature but
  **aren't documented in GUIDE.md**. I only found them by reading
  `blocks.resolve_material`. The README parts table also doesn't list
  `cylinder/sphere/cone/line`.
- Rendering all 3 tiers × 4 views ≈ 23 s for 10k cells. That's fine,
  but `--tier faithful` should be the documented default for iteration
  loops.
