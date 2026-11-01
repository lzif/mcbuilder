# API reference

```python
import mcbuilder as mb
```

Coordinates: **+X east, +Y up, +Z south**. Box corners are inclusive and may be given in any
order. Anywhere a block is accepted you can pass a [material](#materials) instead of one block
string.

## `mb.Build`

```python
BUILD = mb.Build(seed=None, views=None, max_dimensions=(256, 256, 256))
```

| Argument | Meaning |
|---|---|
| `seed` | drives `BUILD.rng()` and weighted palettes; same script + seed = same build |
| `views` | default preview cameras, e.g. `"iso;az200_el025;top"` ([previews](previews.md)) |
| `max_dimensions` | size limit per axis; going past it raises `mb.GridBoundsError` |

A builder script defines a module-level `BUILD` and places blocks inside `with BUILD:`. Placing
outside that block raises `mb.BuildError`.

### Placing blocks

| Method | What it does |
|---|---|
| `set(x, y, z, block)` | one block; last write wins |
| `carve(c1, c2)` | remove everything in the box (cells become *unset*, see below) |
| `place(geometry, at=(0, 0, 0), rotation="NONE")` | stamp a [`Geometry`](#mbgeometry); returns it in absolute coordinates |
| every [shape](#shapes) | `BUILD.box(...)`, `BUILD.roof_gable(...)`, … place the shape and return the placed `Geometry` |

**Unset vs air.** A cell you never placed (or carved) is *unset*: it is not in the `.nbt`, so
pasting leaves whatever was in the world there. `"minecraft:air"` is a real block: with
`mcbuild run --air explicit` it is exported and clears that cell when pasted (an underwater base's
interior, a doorway cut into a hill).

### Reading the build back

All of these work outside `with BUILD:`.

| Method | Returns |
|---|---|
| `get(x, y, z)` | canonical block string, or `None` for unset/air |
| `count(block)` | number of cells holding exactly `block` (property order ignored) |
| `find(block)` | sorted list of `(x, y, z)` holding exactly `block` |
| `bounds()` | `((minx, miny, minz), (maxx, maxy, maxz))` of placed blocks, or `None` |
| `grid` | the underlying `VoxelGrid`; `grid.to_dense()` gives `(array, palette, provenance)` with `array[x, y, z]` (axis 0 = X, never transposed) and `-1` for unset |

### Other methods

| Method | What it does |
|---|---|
| `rng(name=None)` | seeded `random.Random`. `rng("roof")` is an independent stream per name, so editing one part of a script doesn't reshuffle the others |
| `recenter()` | move the build so its XZ center is at the origin |
| `render(out_dir, views=None, *, tier="faithful", region=None)` | render previews from Python; `region=((x0, y0, z0), (x1, y1, z1))` renders only that box |
| `validate(registry)` | `(errors, warnings)` against a `mcbuilder.registry.Registry` (the CLI does this for you) |

## Shapes

Every shape exists twice with **identical arguments**:

- `BUILD.<shape>(...)` places it now and returns the placed `Geometry`.
- `mb.shapes.<shape>(...)` returns a `Geometry` and places nothing; stamp it with
  `BUILD.place(geo, at=..., rotation=...)` as often as you like.

```python
with BUILD:
    roof = BUILD.roof_gable((0, 5, 0), (8, 5, 6), "minecraft:spruce_stairs", ridge="x")
    (_, _, _), (_, peak, _) = roof.bounds()          # size the next thing from what landed

tower = mb.shapes.cylinder((0, 0, 0), 3, 12, "minecraft:stone_bricks", hollow=True)
with BUILD:
    for x in (0, 20):
        BUILD.place(tower, at=(x, 0, 0))
```

| Shape | Arguments | Notes |
|---|---|---|
| `box` | `(c1, c2, block)` | solid box |
| `walls` | `(c1, c2, block)` | the four side walls of the box, no floor or ceiling |
| `pillar` | `(base, height, block)` | column going up from `base` |
| `line` | `(p1, p2, block)` | straight line in any direction, face-connected (no corner-only gaps); also fences, beams, rails |
| `stairs` | `(start, direction, block, *, length=None, target=None, width=1)` | climbs toward `direction`, 1 up per 1 across. Give `length` **or** `target` (the top step's cell). Sets `facing=<direction>`, `half=bottom` |
| `cylinder` | `(center, radius, height, block, *, axis="y", hollow=False, fill=None)` | `axis="x"`/`"z"` lies on its side and grows toward +X/+Z (tunnels, pipes). `fill` fills a hollow interior, e.g. `"minecraft:air"` |
| `sphere` | `(center, radius, block, *, hollow=False, thickness=1, dome=False, fill=None)` | `dome=True` keeps `y >= center.y` |
| `cone` | `(center, radius, height, block, *, hollow=False)` | base disc at `center`, tip `height - 1` above |
| `roof_gable` | `(c1, c2, block, *, ridge, verge=None, eave=None)` | `ridge="x"` or `"z"`; lowest row at `min(c1.y, c2.y)`; rises `ceil(span / 2)` rows. `verge` / `eave` are stair materials for the gable-end columns and the lowest row |
| `roof_hip` | `(c1, c2, block, *, hip, cap=None)` | slopes on all four sides; `hip` is the full block on the corners |

All shapes take an optional `seed=` for palette picks; `BUILD` methods pass the build's seed.

**Computed directions.** `stairs`, `roof_gable` and `roof_hip` set `facing` themselves: pass the
stair block **without** `facing` (passing one is an error). No other shape ever adds or changes
properties. See [blocks and directions](blocks.md).

## Materials

Pass any of these wherever a block is expected:

```python
"minecraft:stone_bricks"                                    # one block
["minecraft:stone_bricks", ("minecraft:mossy_stone_bricks", 0.4)]  # weighted, per-cell speckle
mb.patches([("minecraft:stone_bricks", 3), "minecraft:mossy_stone_bricks"], scale=3)  # clusters
lambda x, y, z: "minecraft:stone" if y < 3 else "minecraft:andesite"                # anything
```

- A **weighted list** picks per cell from a stable hash of `(seed, x, y, z)`. Bare strings
  weigh 1.
- **`mb.patches(palette, scale=4.0, salt="")`** picks with smooth noise, so variants form
  patches about `scale` blocks across. Usually what you want for walls, floors and roofs.
  Change `salt` for a different layout with the same palette.
- A **callable** gets the cell's coordinates and returns a block string.

## `mb.Geometry`

A set of block placements that is not in a build yet. Shapes return one; you can also make one
cell by cell.

| Method | Returns |
|---|---|
| `set(dx, dy, dz, block)` | adds one cell (in place) |
| `a + b` | new geometry with both (later cells win on overlap) |
| `shift(dx, dy, dz)` | new geometry, moved |
| `rotate(rotation="CLOCKWISE_90", anchor=(0, 0, 0))` | new geometry turned about `anchor`; `facing`, `axis` etc. turn with it |
| `mirror(axis="x")` | new geometry mirrored across the `x = 0` (or `z = 0`) plane |
| `carve(c1, c2)` | new geometry without the cells in the box |
| `cells()` | `[(dx, dy, dz, block), ...]` |
| `bounds()` | inclusive bounding box, or `None` |

Rotations: `"NONE"`, `"CLOCKWISE_90"`, `"CLOCKWISE_180"`, `"COUNTERCLOCKWISE_90"` (clockwise seen
from above).

## Errors

All mcbuilder errors derive from `mb.McbuilderError`:

| Error | When |
|---|---|
| `mb.BuildError` | placing outside `with BUILD:`, bad arguments to `Build` methods |
| `mb.GridBoundsError` | a block outside `max_dimensions` |
| `mb.McbuilderError` | bad shape arguments (`ridge="y"`, a stair with `facing`, …), bad material specs |
| `ValueError` | a malformed block string (`"minecraft:oak_stairs[facing"`) |
