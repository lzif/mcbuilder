"""Find air cells that would let the ocean in.

An underwater base exported with ``--air explicit`` replaces water only
where the script placed ``minecraft:air``. Any air cell that touches a cell
the script never placed (which stays ocean water after pasting) floods.

usage: python leak_check.py underwater_base.py
"""

import runpy
import sys

AIR = "minecraft:air"
NEIGHBOURS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def leaks(build) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    """``(air_cell, open_neighbour)`` pairs, sorted."""
    grid = build.grid
    out = []
    for (x, y, z), idx in grid._cells.items():
        if grid._palette[idx] != AIR:
            continue
        for dx, dy, dz in NEIGHBOURS:
            n = (x + dx, y + dy, z + dz)
            if n not in grid._cells:
                out.append(((x, y, z), n))
    return sorted(out)


if __name__ == "__main__":
    found = leaks(runpy.run_path(sys.argv[1])["BUILD"])
    for cell, n in found[:20]:
        print(f"air {cell} touches open water at {n}")
    print(f"{len(found)} leak(s)")
    sys.exit(1 if found else 0)
