"""mcbuilder — Python tooling for AI agents that build Minecraft structures."""

from mcbuilder import parts, preview, views  # noqa: F401  (submodule access as mb.parts etc.)
from mcbuilder.build import Build, BuildError
from mcbuilder.errors import McbuilderError
from mcbuilder.voxels import GridBoundsError

__version__ = "0.1.0"

__all__ = [
    "Build",
    "BuildError",
    "GridBoundsError",
    "McbuilderError",
    "__version__",
    "parts",
    "preview",
    "views",
]
