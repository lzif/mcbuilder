"""mcbuilder — Python tooling for AI agents that build Minecraft structures."""

from mcbuilder import part, parts, preview, preview_trusted, rotation, views  # noqa: F401  (submodule access as mb.part etc.)
from mcbuilder.build import Build, BuildError
from mcbuilder.errors import McbuilderError
from mcbuilder.geometry import Geometry
from mcbuilder.voxels import GridBoundsError

__version__ = "0.1.0"

__all__ = [
    "Build",
    "BuildError",
    "Geometry",
    "GridBoundsError",
    "McbuilderError",
    "__version__",
    "part",
    "parts",
    "preview",
    "preview_trusted",
    "rotation",
    "views",
]
