# Examples

Run any of them from its own folder (each has an `mcbuild.toml`):

```bash
cd examples/homestead
mcbuild run house.py --preview --guide
```

| Folder | What it shows |
|---|---|
| [`homestead/`](homestead/) | four paste-ready structures sharing one palette module: a two-story Tudor `house.py` (jetty, cross gable, dormers, chimney, furnished interior), a `barn.py` with a lean-to forge and cupola, a stone `watchtower.py`, a small `well.py` |
| [`underwater_base/`](underwater_base/) | glass domes and tunnels with air-filled interiors (`cylinder(axis="x", hollow=True, fill="minecraft:air")`); export with `--air explicit`. `leak_check.py` finds air cells that would flood |
| [`crystal_observatory/`](crystal_observatory/) | a floating island with an observatory tower, built mostly from hand-written loops |
| [`waystones/`](waystones/) | five 7 × 7 × 7 variants built from shared `Geometry` pieces (define once, stamp many); uses a custom allowlisted block |
