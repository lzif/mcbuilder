# Design guide

A build that passes `mcbuild check` can still look flat and unfinished. This guide is about
making a **standalone structure** look good: something you paste into a world or build from the
layer guide. There is no terrain here. The structure has to stand on its own, on any flat
ground.

These are techniques, not templates. They work for houses, towers, bases, ships and bridges
alike: take the technique, not the shape.

## The workflow

1. **Massing first.** Block out the big volumes with plain `box`/`walls` and one material. Render
   `iso` and `top` and fix proportions *before* adding any detail. Detail never rescues bad
   proportions.
2. **Frame, then fill.** Posts, beams and corners next; walls fill between them.
3. **Roof and silhouette.**
4. **Material pass**: variation, bands, trim.
5. **Details**: openings, lights, props.
6. **Check each pass** with `--focus` close-ups and `--tier trusted` for directions.

Render after each step. One change per render makes it obvious what helped.

## Proportion and composition

- **Pick one focal point** per structure: an entrance, a tower, a chimney. Everything else
  supports it and stays quieter.
- **Avoid perfect boxes and cubes.** A footprint around 3:2 reads better than a square; vary the
  heights of connected parts.
- **Leave breathing room** between masses. A chimney or annex jammed against the main wall reads
  as a mistake; one block of air or a recess reads as intent.
- **Vary rhythm, don't stamp it.** A rule applied evenly everywhere (shutters on every window, a
  lantern every six blocks) looks generated. Keep the rhythm, then break it on purpose: a
  bigger window over the door, a missing lantern where a tree would be.
- **Asymmetry with balance**: an off-centre wing balanced by a chimney or tower on the other side.

## Structure: frame first

- **Posts and beams define the silhouette**; walls fill between them. Use logs with the right
  `axis`: `y` for posts, `x`/`z` for beams.
- **Exposed joints are free detail.** A different log or a stripped variant where beam meets post
  reads as craftsmanship.
- **Corbel and jetty.** Push an upper floor one block out over the floor below and support it
  with upside-down stairs (`half=top`, back against the wall). The shadow line breaks the box
  for free.
- **Braces belong in big panels.** Diagonal braces only read in panels about 4 × 4 or larger. In
  smaller panels a mid-rail (close studding) looks cleaner than a stepped diagonal blob.

## Roofs and silhouette

The roof is most of what you see from above and from a distance.

- **Never a flat top** on anything meant to look finished. Use stairs (`roof_gable`, `roof_hip`):
  every step catches light.
- **Overhang by at least one block** past the walls.
- **Break the ridge line**: a cross gable over the entrance, dormers, a chimney, a cupola on a long
  barn roof. One vertical accent changes the whole read.
- **Trim the edges.** Big single-material roofs look like a tarp. Give the gable ends a different
  material (`verge=`) and the lowest row a slightly different shade (`eave=`); a dark tile roof
  with wooden bargeboards is a classic.
- **Fill the gable ends** with the wall's frame-and-fill pattern, a king post, a small window.
- **Dormers** need a front at least 3 blocks tall and their own roof in a contrasting verge, or
  they disappear into the main roof.

## Materials

- **Never a large flat single-material surface.** Use `mb.patches(...)` for walls, floors and
  roofs: about two thirds main block, the rest one or two close variants (stone bricks with
  mossy and cracked; spruce planks with stripped spruce).
- **Patches, not speckle.** Per-cell random mixes (a plain weighted list) look like noise on large
  areas. Use `mb.patches` for big surfaces and keep weighted lists for small ones.
- **Band by story**: stone ground floor, timber upper floor, dark roof. Big simple areas are fine
  when they are clearly separated.
- **Two-tone the edges**: light quoins on a dark wall, a dark sill under a light wall.
- **Weather toward the ground**: more moss and cracks near the bottom (a material callable that
  depends on `y`).
- **Check colors in a render.** Names lie: `white_terracotta` is pinkish beige, `calcite` is the
  cleaner white. Render a close-up before committing to a palette.

| Look | Base | Variants | Trim |
|---|---|---|---|
| medieval stone | stone bricks | mossy, cracked stone bricks, andesite | polished andesite, cobblestone |
| timber frame | calcite | smooth quartz, white concrete powder | dark oak logs |
| rustic wood | spruce planks | stripped spruce wood, dark oak planks | stripped spruce logs |
| dark roof | deepslate tile stairs | deepslate brick stairs (eaves) | dark oak stairs (verge) |
| ocean | prismarine bricks | prismarine | dark prismarine, sea lanterns |

## Openings

- **Windows**: glass panes set into the wall plane, open trapdoor shutters beside them, a flower
  box under some of them (leaves resting on a top-half trapdoor, never floating).
- **Doors** get a frame (different log or stone around them), a step up (stairs), and light on
  both sides.
- **Vary window sizes by floor and by importance.** The window over the entrance can be bigger.

## Light

- **Warm point lights on the structure's rhythm**: a lantern on each corner post, flanking each
  door, hanging under the eaves.
- **Lanterns, not torches on walls.** Repeated identical fixtures read as design; scattered torches
  read as mob-proofing.
- **Never a light block as a wall material** (no glowstone walls). Underwater, work sea lanterns
  into the floor or the frame instead.

## Grounding a structure without terrain

A pasted structure should look planted, even on a flat world:

- **A plinth or foundation one block wider** than the walls, of rougher stone (`patches` of
  cobblestone and mossy cobblestone).
- **Steps up to the door**, so the ground floor reads as raised.
- **A few greenery accents on the plinth ledge**: leaf hedges, a flower box; not a garden.
- **Keep everything inside the footprint you'd expect to paste.** Paths, trees and fields belong
  to the world, not to the structure. If a part has to go below ground (a well shaft, a cellar),
  say so in the script's docstring so whoever pastes it lowers the origin.

## Details that sell scale

Barrels, crates, a ladder, a hay bale, a chain with a hanging barrel on a hoist beam, a workbench
by the door. Put them where a person would actually use them, and leave some empty space so they
still read.

## Interiors

Interiors don't show in exterior previews, so check them with `--focus` boxes that stop below
each ceiling. Furnish by room: kitchen against the chimney wall, storage by the door, beds
upstairs. Use stairs plus top slabs for chairs and tables. Keep walkways two blocks wide.

## Anti-patterns

- Large flat single-material walls or roofs.
- Flat tops.
- Light blocks used as walls.
- Floating details: flower boxes, lanterns and shutters with nothing behind or under them.
- Perfect symmetry and identical repeated parts everywhere.
- Parts touching by accident: check `overwritten_placements` in `report.json` and look closely
  where two volumes meet.
- Copying a reference's *shape* instead of its *techniques*.
