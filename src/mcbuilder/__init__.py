"""mcbuilder: build Minecraft structures from Python scripts.

Write a script that fills a :class:`Build`, then use the ``mcbuild`` CLI to
validate it against the real block registry, render previews, export a
structure ``.nbt`` and generate a layer-by-layer build guide.
"""

from mcbuilder import rotation, shapes  # noqa: F401
from mcbuilder.build import Build, BuildError
from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry
from mcbuilder.materials import patches
from mcbuilder.voxels import GridBoundsError

__version__ = "0.2.0"

__all__ = [
    "Build",
    "BuildError",
    "Geometry",
    "GridBoundsError",
    "McbuilderError",
    "patches",
    "rotation",
    "shapes",
    "__version__",
]
