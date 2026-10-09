# bpy design notes — what mcbuilder should steal (and skip)

Source: `~/workspace/blender-modal/BPY_NOTES.md` (Blender 4.2.3 API).
Target: mcbuilder's agent-facing API (`src/mcbuilder/build.py`, `parts.py`).
Status: **IMPLEMENTED in v0.2** (PLAN rev 7, locked 2026-10-09) —
`Geometry` (`src/mcbuilder/geometry.py`), `BUILD.place()`
(`src/mcbuilder/build.py`), `mb.part.*` factories
(`src/mcbuilder/part.py`), layering law documented in
`geometry.py`'s module docstring. This file is now history.

## The core insight

bpy's best design decision is its **layering**:

| bpy layer | What it is | mcbuilder equivalent |
|---|---|---|
| `bpy.data` | Datablocks: pure geometry/material data. No UI, no context. Always works headless. | `VoxelGrid` — the raw voxel store |
| `bmesh` | Composable low-level geometry editing (extrude, subdivide, transform). | `Build.set` / `grid.place` — direct voxel ops |
| `bpy.ops` | High-level operators (UI actions as functions). Validated, keyword-heavy. | `Build.box/walls/roof_gable` + parts catalog |
| modifier stack | Non-destructive parametric ops, re-evaluated on change. | **The script itself** — full deterministic re-run from `seed` |
| `bpy.context` | Implicit active/selected state. The most error-prone layer (all headless gotchas live here). | **Nothing — deliberately.** |

## Steal #1: datablock + instancing (the big one)

bpy: define geometry once, instance many times with different transforms.

```python
mesh = bpy.data.meshes.new("Pillar")      # data: defined once
obj1 = bpy.data.objects.new("P1", mesh)   # instance: linked, placed
obj1.location = (0, 0, 0)
obj2 = bpy.data.objects.new("P2", mesh)
obj2.location = (8, 0, 0)
```

mcbuilder today: parts place voxels immediately at absolute coords. Four
identical pillars = four `pillar()` calls (or a hand-written loop).

Proposed steal — two-phase parts:

```python
p = mb.part.pillar(height=5, block="minecraft:oak_log")  # geometry, places nothing
with BUILD:
    BUILD.place(p, at=(0, 0, 0))
    BUILD.place(p, at=(8, 0, 0))
    BUILD.place(p, at=(0, 0, 8))
    BUILD.place(p, at=(8, 0, 8))
```

- `part.*` returns a `Geometry`: a small voxel grid in **relative** coords
  (origin at its natural anchor, e.g. pillar base center).
- `BUILD.place(geometry, at=(x, y, z))` stamps it into the grid.
- Existing one-shot `BUILD.pillar(base, height, block)` stays as sugar
  (implemented as `place(part.pillar(...), at=base)`).

Why it matters: the windmill has 4 corner pillars, repeated window frames,
repeated railing segments. "Define once, stamp many" is exactly how an
agent should think about symmetric builds — and it mirrors how builders
think ("this pillar design, copy it there"). Also cheaper: geometry
computed once.

## Steal #2: composite parts (collections)

bpy collections group objects; a collection can be instanced as one unit.

mcbuilder mapping: a part may return **multi-piece geometry** stamped as
one unit. E.g. `window_recessed()` = frame + set-back panes + sill in a
single `Geometry`. The agent places one window, not 14 `set()` calls.
This is Steal #1 composed — and it's where the tips-and-tricks backlog
(window frames, roof trims) naturally lands.

## Steal #3: keyword-heavy signatures

bpy: `primitive_cube_add(size=2, location=(0, 0, 0))` — everything keyword,
no positional order to misremember. LLMs mix up positional arg order;
keywords are self-documenting.

mcbuilder convention going forward: **all new public API takes keyword
args** (or keyword-with-defaults). Existing `box(c1, c2, block)` stays
for compat, but new parts use `stairs_run(start=..., direction=...,
length=..., block=...)` style exclusively.

## Steal #4: document the layering as law

bpy works because each layer has a contract: data has no behavior,
bmesh has no validation, ops validate. mcbuilder's emerging layers:

- `voxels.VoxelGrid.place` — raw, no canonicalization (the bmesh layer)
- `Build.set` — canonicalize + provenance (the validated op layer)
- parts — geometry math the agent must not hand-roll
- the script — the modifier stack (re-run = re-evaluate)

Write this into the plan so future API additions land on the right layer
instead of blurring them.

## Explicitly SKIP: bpy.context

`bpy.context` (implicit active/selected object) is where every headless
bpy bug lives — the BPY_NOTES gotchas are 80% context problems. mcbuilder
must never grow implicit placement state ("current position", "last
part"). The plan's "no silent inference" principle is the anti-context
rule. Every placement takes explicit coordinates. No exceptions.

## Verdict

- **Adopt**: Steal #1 (geometry/instancing split) — highest value, windmill-shaped.
- **Adopt**: Steal #2 (composite parts) — natural home for the tricks backlog.
- **Adopt**: Steal #3 (keyword convention) + #4 (layering law) — cheap, prevents drift.
- **Reject**: anything resembling `bpy.context` — implicit state is the enemy.
- **Not needed**: a lazy modifier system — deterministic script re-run already
  gives non-destructive re-evaluation for free.
