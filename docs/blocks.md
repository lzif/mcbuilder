# Blocks and directions

## Block strings

```python
"minecraft:stone"
"minecraft:oak_stairs[facing=north,half=top]"
"minecraft:chest[facing=east]{Items:[{Slot:0b,id:\"minecraft:apple\",count:3}]}"
```

`name[properties]{nbt}`. Property order never matters: `[half=top,facing=north]` and
`[facing=north,half=top]` are the same block. A malformed string raises `ValueError` right at the
line that placed it.

**Leave out what you don't care about.** Properties you omit take the vanilla default when the
structure is pasted (`waterlogged=false`, `half=bottom`, `axis=y`, …). `mcbuild check` validates
only the properties you wrote, each against the block's legal values for your Minecraft version.
Write a property explicitly whenever its default matters to the design.

**NBT** (chest contents, sign text) is syntax-checked and written to the `.nbt` as given.

**Custom blocks** from a mod or plugin: add them to `allowlist` in `mcbuild.toml`. They pass
validation with a warning and go into the `.nbt` untouched; previews draw them as magenta cubes.

## Coordinates

**+X = east, +Y = up, +Z = south.** North is −Z, so in a top-down view north is up.

In the exported `.nbt` and in build guides, positions count from the build's north-west bottom
corner (its smallest x, y and z), whatever coordinates the script used.

## Directions

mcbuilder never guesses a direction. `set`, `box`, `walls`, `pillar`, `line`, the round shapes
and materials all place the block string exactly as written. Only shapes whose geometry defines
a direction compute one:

| Shape | Rule |
|---|---|
| `stairs(start, direction, ...)` | every step gets `facing=<direction>`, `half=bottom`: the tall back is uphill, like stairs a player placed while walking up |
| `roof_gable(..., ridge=...)` | every row faces uphill toward the ridge. `ridge="x"`: the north slope faces `south`, the south slope faces `north`; `ridge="z"`: west slope `east`, east slope `west` |
| `roof_hip(...)` | each side faces uphill toward the middle; corners use the `hip` block |

What the properties mean, for blocks you place yourself:

| Block | Property | Meaning |
|---|---|---|
| stairs | `facing` | side the tall back is on (the direction you climb toward) |
| stairs | `half=top` | upside down (corbels, eaves, overhang trim) |
| logs, pillars, chains, hay | `axis` | direction the block runs: `y` upright, `x` east-west, `z` north-south |
| doors | `facing` | direction a player faced when placing it; place both `half=lower` and `half=upper` |
| beds | `facing` | from foot to head; place `part=foot` and `part=head` |
| trapdoors | `facing`, `half`, `open` | open trapdoors hang on the side opposite `facing` (so `facing=north` shutters sit flat against a wall to their south) |
| wall torches, wall signs | `facing` | direction away from the supporting wall |

Fences, walls, panes and iron bars connect to their neighbors by themselves when pasted, and the
faithful preview draws the same connections, so you never set `north=true` and friends by hand.

**Checking directions.** The `trusted` preview tier draws stairs as wedges, logs with an axis
band, doors and trapdoors as plates and so on, in flat colors: the quickest way to catch a wrong
`facing`. Its report lists any directional block it can't draw truthfully.

## Rotation and mirroring

`BUILD.place(geo, at=..., rotation="CLOCKWISE_90")` and `geo.rotate(...)` turn positions *and*
block states: `facing` cycles north → east → south → west for each 90° clockwise, `axis` swaps
`x`/`z`, sign and banner `rotation` shift by 4, and connection properties move with the sides.
`half`, `shape`, `hinge` and the rest don't change. This is the same table a structure paste
uses, so a design that looks right here looks right at every paste rotation.

`geo.mirror("x")` / `geo.mirror("z")` flips positions and swaps `facing` (east↔west or
north↔south). It does not change stair `shape` corners or door `hinge`, which have no single
correct mirror; check those in the trusted preview.
