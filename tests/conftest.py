"""Make the in-repo mcbuilder package importable for tests (no install needed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
