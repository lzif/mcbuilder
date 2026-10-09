# mcbuilder — REPLAN DRAFT (proposed rev 7)

> **SUPERSEDED.** This draft was locked as PLAN.md rev 7 by Luki on
> 2026-10-09 ~17:36 WIB. Do not implement from this file — the locked
> `PLAN.md` is authoritative. Kept for history only.

Status: **DRAFT for Luki's review** — not locked, not reviewed. Prepared
2026-10-09 ~10:00 WIB as the "bikin plan" step for his "plan ulang
mcbuilder" call. Review path per standing workflow: fresh-context
subagent review → fix → re-review → his explicit lock → implement.

## What changed since rev 6 (why a replan, not a patch)

Three inputs landed after rev 6 that change the calculus:

1. **Real consumer confirmed** (Luki, 2026-10-09 ~08:25): mcbuilder's
   `.nbt` output feeds his **LostQoL plugin** — `StructurePaster.
   placeAnimated()` already loads bundled `.nbt` from plugin resources
   and pastes animated, server-side. Pipeline:
   `mcbuilder → .nbt → plugin resources → server-side paste → survival
   server` (Bedrock-friendly, no creative/WorldEdit/hologram/Litematica).
   This **answers the 2nd devil's advocate's "serializer without a
   deserializer" charge** (§12, rev 6): the deserializer exists and works.
2. **Direction-correctness stakes went up**: a wrong-facing block in the
   `.nbt` is now a wrong-facing block *on the server* (the v8 stair
   lesson, learned the hard way). The "one direction-trusted preview"
   point from the external roast becomes the **#1 technical priority** —
   nothing `.nbt`-shaped goes into production use until a preview can be
   trusted on facings.
3. **bpy design brief** (`docs/bpy-design-notes.md`, 2026-10-09): the
   planned API redesign — datablock+instancing split, composite parts,
   keyword-heavy signatures, documented layering law, and an explicit
   ban on anything resembling `bpy.context` (implicit state).

Consequence: rev 6's §2/§3/§7/§8 describe a *different product* than the
one Luki now wants (freehand survival building from design output).
Patching sentences would leave contradictions; the affected sections
are rewritten below. Unchanged sections (0, 1, 4.1, 4.4-views/framing,
4.5, 4.6, 5, 6, 9, 10, 11) carry over as-is unless review says otherwise.

## Revised §2 — Goal

`agent writes builder script → mcbuilder validates → exports .nbt →
renders direction-trusted previews → agent iterates on what it sees →
.nbt ships in LostQoL resources → server-side animated paste.`

mcbuilder now has **two output tracks**, and the plan stops conflating
them:

- **Track A — production pipeline (primary):** structures that must land
  *on the server exactly as designed* (waystone upgrades, spawn builds,
  future server structures). Output: `.nbt` → plugin resources →
  `StructurePaster.placeAnimated()`. Direction-correctness is load-
  bearing here; the direction-trusted preview (§4.4 faithful tier,
  direction-scoped MVP) is the gate before any `.nbt` enters this track.
- **Track B — design output (kept):** previews + `block_counts` material
  list for things Luki builds **freehand in survival** (the windmill
  acceptance, personal projects). No paste, no plugin involvement.

Track A is the new center of gravity. Track B is unchanged from rev 6.

## Revised §3 — Non-goals (v1)

- No GUI editor, no game client, no in-game bot placement, no WorldEdit,
  no creative pasting, no Litematica, no hologram/ghost-block guides.
  Deploy path for server structures is the Track A pipeline (§2) —
  **freehand manual building is no longer the deploy path for anything
  that ships via `.nbt`** (it remains the *build* method for Track B).
- No redstone simulation, no entity AI, no terrain generation beyond
  simple noise fill (deferred).
- Entities (armor stands, item frames, paintings) are out of v1 scope.
- Intentional air-clearing is out of v1 — manual work, not a bug.
- **No implicit placement state, ever** (the anti-`bpy.context` rule —
  see revised §4): no "current position", no "last part", no silent
  direction inference beyond the documented per-helper rules in §4.2.

## Revised §4 — Architecture additions (bpy steals)

Adopted from `docs/bpy-design-notes.md` (all four "Adopt" verdicts;
`bpy.context`-shaped ideas explicitly rejected):

**Steal #1 — geometry/instancing split (the big one).** Parts become
two-phase: `mb.part.pillar(height=5, block=...)` returns a `Geometry`
(small voxel grid in *relative* coords, origin at its natural anchor —
e.g. pillar base center; places nothing). `BUILD.place(geometry,
at=(x, y, z))` stamps it into the grid. Existing one-shot
`BUILD.pillar(base, height, block)` stays as sugar, implemented as
`place(part.pillar(...), at=base)`. Rationale: the windmill's 4 corner
pillars, repeated window frames, repeated railing segments — "define
once, stamp many" is how builders think, and geometry computes once.

**Steal #2 — composite parts.** A part may return multi-piece geometry
stamped as one unit: `window_recessed()` = frame + set-back panes +
sill in a single `Geometry`. This is Steal #1 composed — and it's where
the tips-and-tricks backlog (window frames, roof trims, `wall_trim`,
`roof_overhang`) naturally lands. A composite part that simplifies by
dropping detail fails the §10 thesis; composites must preserve detail.

**Steal #3 — keyword-heavy signatures.** All new public API takes
keyword args (or keyword-with-defaults) exclusively:
`stairs_run(start=..., direction=..., length=..., block=...)`. LLMs mix
up positional order; keywords are self-documenting. Existing
`box(c1, c2, block)` stays for compat.

**Steal #4 — layering as law.** Documented contract per layer (future
API additions must land on the right layer, not blur them):

| layer | contract |
|---|---|
| `voxels.VoxelGrid.place` | raw, no canonicalization (bmesh) |
| `Build.set` | canonicalize + provenance (validated op) |
| `mb.part.*` | geometry math the agent must not hand-roll |
| the script | the modifier stack — deterministic re-run = re-evaluation |
| `BUILD.place` | stamping only: no geometry math, no validation beyond bounds |

**Rejected:** anything resembling `bpy.context` — no implicit "current
position" / "selected part" / ambient state. The plan's "no silent
inference" principle (§4.2) is the anti-context rule. Every placement
takes explicit coordinates. No exceptions.

## Revised §7 — Acceptance (two tracks)

**Gate 1 — waystone upgrade, Track A (NEW, first):** the small, real
consumer that proves the pipeline end-to-end *before* the windmill.

1. Author the waystone (v9 — includes the stair fix that was previously
   manual) as an mcbuilder script using parts.
2. Export `.nbt` → drop into LostQoL plugin resources →
   `StructurePaster.placeAnimated()` pastes on a test area.
3. **Verify in-game: every facing correct** (stairs, logs, directional
   blocks). This is the direction-trust gate made concrete — the exact
   bug class that bit v8.
4. Script stays small (parts thesis holds on a real, small build).

**Gate 2 — Ravenwick Windmill, Track B (unchanged scope, demoted
order):** as rev 6 §7 — agent authors with parts, previews → iterate,
Luki builds freehand in survival on Bedrock from design output,
compare vs reference (proportions, detail, directions), script stays
small vs the 403-step reference.

Rationale for the order: Gate 1 exercises the *production* path with a
build Luki already knows block-for-block (the waystone), so failures
are diagnosable; Gate 2 exercises the *parts thesis* at scale. A
pipeline that can't paste a waystone correctly has no business
attempting a windmill.

## Revised §8 — Milestones

- **v0.1** — shipped (as rev 6): core, validator, `.nbt` export +
  round-trip gate, fast preview, `report.json`. 220/220 tests,
  review+roast clean.
- **v0.2** — **direction-trusted preview + bpy API.** (a) Faithful
  renderer MVP scoped to **direction-correctness only** (§4.4 MVP —
  variant resolution, model x/y rotations, per-face textures; deferred
  list unchanged). This is the #1 priority: nothing enters Track A
  without it. (b) Geometry/instancing API (`mb.part.*` + `BUILD.place`),
  keyword-only convention for new API, layering law documented.
  **Gate: `.nbt` → StructurePaster → test paste of the demo hut, all
  facings verified in-game against the direction-trusted preview.**
  The preview and the paste must agree — that agreement *is* the trust.
- **v0.2.5** — **waystone upgrade end-to-end (Gate 1, §7).**
- **v0.3** — windmill end-to-end (Gate 2, §7) + remaining parts
  (`blade`, `timber_frame_wall`, `arch`, `lantern_row`).

Deferred exports (`.schem`, `.mcfunction`, datapack) unchanged: only if
a real consumer needs them.

## Revised §12 — strategic decision: resolution proposed

The 2nd devil's advocate's sharpest charge — "serializer without a
deserializer" — is **answered**: `StructurePaster.placeAnimated()` is
the deserializer, it exists, it works, and Luki named the first
production use (waystone upgrade). The other DA observations stand and
are handled, not dismissed:

- *"The user is hypothetical — no agent has run the loop."* → Luki's
  plugin is now the first real consumer; the waystone gate (v0.2.5) is
  the first real run of the export path. The full agent loop (vision
  critique) is still prospective — honestly labeled.
- *"Parts leverage is prospective."* → unchanged; Gate 1 uses existing
  parts + Steal #1/#2 on a small build, which is the cheapest real test
  of the thesis before windmill-scale catalog work.
- *Opportunity cost* (Kwita, finance baseline Oct 17, VM migration
  Dec 1) → unchanged; noted. v0.2 is deliberately narrow so the cost
  stays bounded.

**Recommendation: CONTINUE with the narrowed v0.2 scope** (direction-
trusted preview + bpy API + waystone gate), then re-examine before
v0.3. The shrink option's core complaint is resolved; killing now would
waste a working validator, a tested exporter, and a named production
consumer.

Options for Luki (his call, as always): **lock this replan** (→ v0.2
implementation) · amend-then-lock · kill · shrink.

---

*Prepared 2026-10-09 ~10:00 WIB by Nyx (research stage) from: rev 6
PLAN.md (`~/workspace/mcbuilder/PLAN.md`), `docs/bpy-design-notes.md`,
Luki's 2026-10-09 ~08:25 intent statement (server-side paste via
LostQoL), and the "plan ulang mcbuilder" call at ~09:36 WIB.*
