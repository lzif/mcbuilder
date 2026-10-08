"""report.json builder (PLAN rev 5, section 4.6).

Schema::

    {
      "errors":   [{"block": str, "message": str,
                    "suggestions": [...], "at": "waystone.py:42"|null}],
      "warnings": [...],
      "block_counts": {"minecraft:stone": 12, ...},
      "dimensions": [x, y, z] | null,          # post-crop bbox
      "views":    [{"file": "az000_el025.png", "azimuth": 0.0,
                    "elevation": 25.0, "label": "az000_el025",
                    "directions_untrusted": true}],
      "run_dir": "dist/run-003"
    }

Every fast-tier preview is flagged ``directions_untrusted: true``
(PLAN section 4.4) — the fast renderer cannot show facing or connection
state, so a preview must never be trusted for block directions.
"""

from __future__ import annotations

import json
from pathlib import Path


def view_entry(*, file: str, view, directions_untrusted: bool = True) -> dict:
    """Build one ``views[]`` entry from a View-like object.

    ``view`` needs ``azimuth``, ``elevation`` and ``label`` attributes
    (see mcbuilder.views.View); ``file`` is the PNG filename.
    """
    return {
        "file": file,
        "azimuth": view.azimuth,
        "elevation": view.elevation,
        "label": view.label,
        "directions_untrusted": directions_untrusted,
    }


def build_report(*, errors: list[dict], warnings: list[dict],
                 block_counts: dict[str, int],
                 dimensions: tuple[int, int, int] | None,
                 views: list[dict], run_dir: str) -> dict:
    """Assemble the report.json dict. Inputs are copied, never mutated."""
    return {
        "errors": [dict(e) for e in errors],
        "warnings": [dict(w) for w in warnings],
        "block_counts": dict(block_counts),
        "dimensions": list(dimensions) if dimensions is not None else None,
        "views": [dict(v) for v in views],
        "run_dir": run_dir,
    }


def write_report(report: dict, path: str | Path) -> None:
    """Write the report as JSON (indent=2). Creates parent dirs as needed."""
    p = Path(path)
    if p.parent != Path("."):
        p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


__all__ = ["build_report", "view_entry", "write_report"]
