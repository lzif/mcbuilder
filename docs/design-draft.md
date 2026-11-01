# Design guide (draft)

> **Status: draft.** Distilled from six medieval houses by experienced builders (imported with
> `mcbuild import` and measured) and tested once on [`examples/storehouse`](../examples/storehouse/).
> It covers one style family: medieval timber-frame. Expect changes; the open items are listed
> at the end.

Everything here is about **standalone structures** (no terrain): something you paste or build
from the layer guide.

## What the references have in common, in numbers

| Measure | Six references | Our first attempt (homestead house) |
|---|---|---|
| Upside-down stairs (`half=top`) among all stairs | 22–79% | 4% |
| Thin detail blocks (trapdoors, fences, buttons, chains, lanterns, signs) | 6–14% of all blocks | 5% |
| Horizontal logs (`axis=x/z`) among logs | up to 45% | few |
| Roof material | dark deepslate in 5 of 6, spruce in 1 | deepslate |

The two clearest gaps were upside-down stairs and thin detail. Most of the techniques below are
about those.

## 1. Frame first

- **Posts**: `stripped_spruce_log[axis=y]` (or stripped dark oak) at every corner and every 3–5
  blocks along each wall.
- **Beams**: horizontal logs (`axis=x` / `axis=z`) at every floor line, running along the post
  plane.
- The frame is a different color from the infill, always: dark wood on white plaster, or light
  stripped wood on grey stone.

## 2. Two materials, stacked

- **Ground floor: stone.** A mix of 4–5 close stones (`stone_bricks`, `cobblestone`,
  `mossy_stone_bricks`, `cracked_stone_bricks`, `andesite`) with `mb.patches(..., scale=1.5)`.
  Set the stone **one block behind the posts**, so the posts stand proud.
- **Upper floor: plaster or wood.** `calcite` with some `diorite` (`patches`, scale 2), or
  planks between dark posts. Set the plaster **flush with the posts**. A second recess here
  turns every bay into an empty box.
- **Plinth**: one block wider than the walls, darker and rougher than the walls
  (`cobbled_deepslate`, `cobblestone`, `deepslate_bricks`).

## 3. Jetty: the upper floor sticks out

The upper floor sits one block further out than the ground floor. Under the overhang runs a
band that **alternates** an upside-down stair and a top slab:

```
y=6   [planks deck — one block wider on every side]
y=5   [stair^][slab^][stair^][slab^]...   ← outside the ground-floor beam
y=1-4 [post] [stone, 1 in] [post]
```

The stair is `dark_oak_stairs[half=top]` facing the wall (its tall side against the building).

## 4. Roof

- **Steep and thick.** A stair surface (`roof_gable`) with a full block under every stair, so the
  roof reads as a slab, not a sheet. Mix 2–3 roof stairs with `patches`
  (`deepslate_brick_stairs`, `cobbled_deepslate_stairs`, `deepslate_tile_stairs`).
- **Wooden edges, two blocks deep.** Dark oak stairs on the verge and the eave
  (`verge=`, `eave=`), with dark oak planks underneath.
- **Overhang** at least one block past the upper walls on every side.
- **Decorate the gable peaks**, every time. Pick one:
  - crossed beam "horns": the verge stairs continue 1–2 blocks past the ridge on both slopes;
  - a beam end sticking out of the gable with a chain and a hanging lantern;
  - a finial (wall block + lightning rod).
- **Fill the gable ends** with the upper-floor frame: king post, slope timbers, plaster, a small
  window.
- **Break the roof**: a wall dormer or a cross gable on the front. On a long roof, add one
  vertical accent (chimney, cupola).

## 5. Windows

```
   [lintel: stair^ facing in]
[td][glass][td]        td = trapdoor, open, facing out (flat against the wall)
   [planter: dirt + plant, trapdoor front, stair^ under it]
```

- Glass panes (or iron bars on a storage floor) in the wall plane.
- Open trapdoor shutters on both sides, one block out.
- An upside-down stair as lintel above.
- Flower boxes on some windows, not all: dirt or rooted dirt with plants, a trapdoor as the
  front, an upside-down stair underneath as a bracket.

## 6. Thin details (aim for 6–14% of all blocks)

- Buttons on posts as rivets.
- Fences standing vertically beside posts in the ground-floor recesses.
- Lanterns: hanging under every eave corner and from beam ends on chains; one on a fence post on
  each side of the main door.
- Fence plus fence-gate railings on balconies and landings.

## 7. Give it a purpose

The function shows on the outside. For a storehouse:

- big double doors with a heavy frame, and a loading dock with barrels and hay;
- a loft door with a hoist (beam, chain, hanging barrel);
- barred windows downstairs;
- a lean-to for logs;
- a vent cupola on the ridge.

Pick the equivalent props for other buildings.

## Process that worked

1. Start from a reference: `mcbuild import` a builder's `.nbt`, read the header numbers, and
   render close-ups (`--focus`) of a facade and a roof edge.
2. Read cross-sections (one `x` or `z` column, all `y`) to see the layering, then copy the
   *technique*, not the shape.
3. Build, render from three sides, and compare against the reference **side by side**.
4. Count: upside-down stairs and thin details are easy to measure and easy to forget.

## Open items (minor, to revisit)

- The upper-floor frame is still sparser than the references; posts could be denser, with more
  thin detail on the plaster.
- Small roofs (lean-tos, porches) still come out flat and plain.
- A cupola built from `roof_hip` looks blocky; a hand-shaped small roof would fit better.
- Greenery climbing walls and roofs (vines, leaves) appears in 4 of 6 references and is not
  covered yet.
- Only one style (medieval timber-frame) is covered. Other styles need their own references.
