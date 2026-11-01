"""Small roofed well. The shaft goes 3 blocks below y = 0, so dig before pasting
(or paste with the structure's origin 3 blocks lower).
"""

import mcbuilder as mb

from common import HANGING_LANTERN

BUILD = mb.Build(seed=1207, views="iso;az200_el025")

with BUILD:
    BUILD.box(
        (-1, -3, -1),
        (1, 1, 1),
        mb.patches([("minecraft:mossy_cobblestone", 2), "minecraft:cobblestone"], scale=1.5),
    )
    BUILD.box((0, -3, 0), (0, 0, 0), "minecraft:water")
    BUILD.set(0, 1, 0, "minecraft:air")
    for x, z in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        BUILD.pillar((x, 2, z), 2, "minecraft:spruce_fence")
    BUILD.roof_hip((-1, 4, -1), (1, 4, 1), "minecraft:spruce_stairs", hip="minecraft:spruce_planks")
    BUILD.set(0, 3, 0, "minecraft:iron_chain[axis=y]")
    BUILD.set(0, 2, 0, HANGING_LANTERN)
