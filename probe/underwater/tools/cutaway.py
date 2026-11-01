import runpy, sys
ns = runpy.run_path(sys.argv[1]); B = ns["BUILD"]; mode = sys.argv[2]
(x0,y0,z0),(x1,y1,z1) = B.grid.bounds()
with B:
    if mode == "cut":      # section: remove everything above y=4 except seabed life
        B.carve((x0, 5, z0), (x1, y1, z1))
        B.carve((x0, 2, z0), (x1, 4, -1))  # also slice the south... keep north half low
    else:                   # ocean context: water in every unset cell up to y=12
        for x in range(x0, x1+1):
            for z in range(z0, z1+1):
                if (x-4)**2 + (z+4)**2 > 26**2: continue
                for y in range(1, 13):
                    if B.get(x,y,z) is None and (x,y,z) not in B.grid._cells:
                        B.set(x,y,z,"minecraft:water")
print(B.render(f"/tmp/uw_{mode}", views=["iso","az225_el040"], tier="faithful", title=f"underwater {mode}"))
