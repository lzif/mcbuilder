"""Leak check: explicit air face-adjacent to an UNSET cell = ocean floods in."""
import runpy, sys, collections
ns = runpy.run_path(sys.argv[1]); B = ns["BUILD"]
cells = {k: B.grid._palette[v] for k, v in B.grid._cells.items()}
leaks = collections.Counter(); ex = {}
NEED_WATER = ("kelp", "seagrass", "coral", "sea_pickle")
dry_life = []
for (x,y,z), b in cells.items():
    nb = [(x+1,y,z),(x-1,y,z),(x,y+1,z),(x,y-1,z),(x,y,z+1),(x,y,z-1)]
    if b == "minecraft:air":
        for n in nb:
            if n not in cells:
                key=(x//4*4,y,z//4*4); leaks[key]+=1; ex[key]=(x,y,z,n)
    if any(t in b for t in NEED_WATER) and "_block" not in b and any(cells.get(n)=="minecraft:air" for n in nb):
        dry_life.append(((x,y,z),b))
print("air cells leaking to ocean:", sum(leaks.values()))
for k,c in leaks.most_common(10): print("  ", ex[k], c)
print("water-life touching air:", dry_life[:10])
