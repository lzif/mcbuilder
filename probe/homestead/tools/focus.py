"""Close-up render: copy a sub-box of a build into a fresh Build and render it.

usage: python focus.py SCRIPT x0 y0 z0 x1 y1 z1 OUTDIR [views]
(mcbuilder has no crop/zoom view, so details of big builds are unreadable.)
"""
import runpy, sys
import mcbuilder as mb
script, *c, out = sys.argv[1:9]
views = sys.argv[9] if len(sys.argv) > 9 else "az225_el030;az045_el030"
x0, y0, z0, x1, y1, z1 = map(int, c)
src = runpy.run_path(script)["BUILD"]
g = src.grid
B = mb.Build(seed=0)
with B:
    for (x, y, z), idx in g._cells.items():
        if x0 <= x <= x1 and y0 <= y <= y1 and z0 <= z <= z1:
            B.set(x, y, z, g._palette[idx])
print(B.render(out, views=views, tier="faithful", title="close-up"))
