"""Diff two ``mcbuild run`` outputs (GitHub issue #1, item 5).

Compares the voxel data stored in each run's ``.nbt`` deploy artifact
(located via ``report.json``'s ``artifacts``) and reports added /
removed / replaced cells, plus a side-by-side preview comparison image.

Coordinate frame: the .nbt stores cell positions as offsets from each
run's own bbox minimum, so the diff is anchored at each run's bbox
origin. A build that moved wholesale reports as identical; a build whose
bbox *origin* shifted (e.g. a cell added on the negative side) compares
against the shifted origin. For iteration diffs, re-run the same script
in place — the origin then only moves when the build itself changed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import nbtlib
from PIL import Image, ImageDraw, ImageFont

from mcbuilder import blocks as blocks_mod
from mcbuilder import voxels as voxels_mod
from mcbuilder.errors import McbuilderError

__all__ = [
    "DiffError",
    "VoxelDiff",
    "resolve_run_dir",
    "load_run_voxels",
    "diff_voxel_maps",
    "diff_run_dirs",
    "format_diff",
    "comparison_image",
]


class DiffError(McbuilderError):
    """A diff that cannot run: unknown run id, missing artifact, ..."""


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class VoxelDiff:
    """Cell-level diff between two runs (A = old, B = new)."""

    added: list[tuple[tuple[int, int, int], str]]  # pos, block (in B only)
    removed: list[tuple[tuple[int, int, int], str]]  # pos, block (in A only)
    changed: list[tuple[tuple[int, int, int], str, str]]  # pos, old, new
    cells_a: int  # non-air cells in run A
    cells_b: int  # non-air cells in run B

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def resolve_run_dir(runs_dir: str | Path, run_id: str) -> Path:
    """Resolve a run id (``run-001`` or bare ``001``) to its directory.

    Raises :class:`DiffError` for malformed ids and unknown runs.
    """
    raw = str(run_id).strip()
    if not raw or raw != Path(raw).name or raw.startswith("."):
        raise DiffError(f"invalid run id: {run_id!r}")
    base = Path(runs_dir)
    candidates = [raw]
    if not raw.startswith("run-"):
        candidates.append(f"run-{raw}")
        if raw.isdigit():
            # Bare numbers are zero-padded run ids: "1" -> "run-001".
            candidates.append(f"run-{int(raw):03d}")
    for name in candidates:
        p = base / name
        if p.is_dir():
            return p
    raise DiffError(f"unknown run: {raw} (no such directory in {base})")


def _artifact_nbt_path(run_dir: Path, report: dict) -> Path:
    for art in report.get("artifacts") or []:
        if art.get("format") == "nbt" and art.get("file"):
            return run_dir / art["file"]
    # Tolerate hand-made or older run dirs: exactly one .nbt is unambiguous.
    candidates = sorted(run_dir.glob("*.nbt"))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise DiffError(
            f"{run_dir.name}: no .nbt artifact "
            "(runs with validation errors export none — diff needs two clean runs)"
        )
    raise DiffError(
        f"{run_dir.name}: several .nbt files and report.json names none — "
        "cannot pick one"
    )


def _palette_canonical(entry) -> str:
    """Rebuild the canonical block string for one nbt palette entry.

    The writer stores ``Name`` + sorted ``Properties`` (block-entity NBT
    is stripped at export); re-canonicalizing gives the same key the
    grid palette used, so equal blocks compare equal.
    """
    name = str(entry["Name"])
    props = entry.get("Properties")
    if props:
        kv = ",".join(
            f"{k}={v}"
            for k, v in sorted((str(k), str(v)) for k, v in props.items())
        )
        return blocks_mod.canonicalize(f"{name}[{kv}]")
    return blocks_mod.canonicalize(name)


def load_run_voxels(run_dir: str | Path) -> dict[tuple[int, int, int], str]:
    """Load a run's voxel map from its ``.nbt`` artifact.

    Returns ``{(x, y, z): canonical_block}`` with positions as bbox-min
    offsets (the .nbt's own frame — see the module docstring) and air
    cells excluded, mirroring the default export. Raises
    :class:`DiffError` on anything unreadable.
    """
    run_dir = Path(run_dir)
    if not run_dir.is_dir():
        raise DiffError(f"not a run directory: {run_dir}")
    report_path = run_dir / "report.json"
    if not report_path.is_file():
        raise DiffError(f"{run_dir} has no report.json — not an mcbuild run dir")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise DiffError(f"{run_dir.name}: cannot parse report.json: {e}") from None
    nbt_path = _artifact_nbt_path(run_dir, report)
    if not nbt_path.is_file():
        raise DiffError(f"{run_dir.name}: artifact not found: {nbt_path.name}")
    try:
        f = nbtlib.load(str(nbt_path), gzipped=True)
    except Exception as e:  # noqa: BLE001 - surfaced as a clean message
        raise DiffError(f"{run_dir.name}: cannot read {nbt_path.name}: {e}") from None
    try:
        palette = [_palette_canonical(entry) for entry in f["palette"]]
        cells: dict[tuple[int, int, int], str] = {}
        for b in f["blocks"]:
            pos = tuple(int(v) for v in b["pos"])
            block = palette[int(b["state"])]
            if blocks_mod.parse(block)[0] == voxels_mod.AIR:
                continue  # air is "empty" in both frames
            cells[pos] = block
    except (KeyError, IndexError, ValueError, TypeError) as e:
        raise DiffError(f"{run_dir.name}: malformed {nbt_path.name}: {e}") from None
    return cells


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def diff_voxel_maps(
    a: dict[tuple[int, int, int], str],
    b: dict[tuple[int, int, int], str],
) -> VoxelDiff:
    """Cell-level diff between two voxel maps (A = old, B = new)."""
    added: list[tuple[tuple[int, int, int], str]] = []
    removed: list[tuple[tuple[int, int, int], str]] = []
    changed: list[tuple[tuple[int, int, int], str, str]] = []
    for pos in sorted(set(a) | set(b)):
        in_a, in_b = pos in a, pos in b
        if in_a and not in_b:
            removed.append((pos, a[pos]))
        elif in_b and not in_a:
            added.append((pos, b[pos]))
        elif a[pos] != b[pos]:
            changed.append((pos, a[pos], b[pos]))
    return VoxelDiff(
        added=added, removed=removed, changed=changed,
        cells_a=len(a), cells_b=len(b),
    )


def diff_run_dirs(
    a_dir: str | Path, b_dir: str | Path
) -> VoxelDiff:
    """Load both runs' voxel maps and diff them (A = old, B = new)."""
    return diff_voxel_maps(load_run_voxels(a_dir), load_run_voxels(b_dir))


# ---------------------------------------------------------------------------
# text report
# ---------------------------------------------------------------------------

def _n(n: int, singular: str, plural: str | None = None) -> str:
    """``"1 changed cell"`` / ``"4 changed cells"`` (plural defaults to +s)."""
    word = singular if n == 1 else (plural if plural is not None else singular + "s")
    return f"{n} {word}"


def format_diff(
    diff: VoxelDiff, a_id: str, b_id: str, *, max_entries: int = 30
) -> str:
    """Render the human-readable diff report (printed to stdout by the CLI)."""
    lines = [f"diff {a_id} -> {b_id}"]
    if diff.is_empty:
        lines.append(f"  no differences ({_n(diff.cells_a, 'cell')} in both)")
        return "\n".join(lines)
    lines.append(
        f"  {_n(diff.total, 'changed cell')}: "
        f"{len(diff.added)} added, {len(diff.removed)} removed, "
        f"{len(diff.changed)} replaced "
        f"({diff.cells_a} -> {diff.cells_b} cells)"
    )
    entries: list[tuple[str, tuple[int, int, int], str, str | None]] = (
        [("+", pos, new, None) for pos, new in diff.added]
        + [("-", pos, old, None) for pos, old in diff.removed]
        + [("~", pos, old, new) for pos, old, new in diff.changed]
    )
    for sym, pos, old, new in entries[: max(0, max_entries)]:
        xyz = ", ".join(str(v) for v in pos)
        if new is None:
            lines.append(f"  {sym} ({xyz}) {old}")
        else:
            lines.append(f"  ~ ({xyz}) {old} -> {new}")
    rest = len(entries) - min(len(entries), max(0, max_entries))
    if rest:
        lines.append(f"  ... {_n(rest, 'more change')} not shown (use --max N)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# side-by-side comparison image
# ---------------------------------------------------------------------------

def _first_common_view(
    a_dir: str | Path, b_dir: str | Path
) -> tuple[Path, Path] | None:
    """First preview view label present in both runs' reports and on disk."""

    def views(run_dir: str | Path) -> dict[str, Path]:
        rp = Path(run_dir) / "report.json"
        try:
            report = json.loads(rp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        out: dict[str, Path] = {}
        for v in report.get("views") or []:
            label, rel = v.get("label"), v.get("file")
            if label and rel and label not in out:
                out[label] = Path(run_dir) / rel
        return out

    va, vb = views(a_dir), views(b_dir)
    for label, pa in va.items():
        pb = vb.get(label)
        if pb is not None and pa.is_file() and pb.is_file():
            return pa, pb
    return None


def comparison_image(
    a_dir: str | Path,
    b_dir: str | Path,
    diff: VoxelDiff,
    out_path: str | Path,
    *,
    a_id: str | None = None,
    b_id: str | None = None,
) -> Path | None:
    """Compose the two runs' matching preview PNGs side by side.

    Title band carries the change counts; each panel is captioned with
    its run id. Returns the written path, or ``None`` when the runs
    share no preview view (or the PNGs can't be read) — the caller then
    falls back to the textual report alone.
    """
    pair = _first_common_view(a_dir, b_dir)
    if pair is None:
        return None
    a_id = a_id or Path(a_dir).name
    b_id = b_id or Path(b_dir).name
    try:
        imgs = [Image.open(p).convert("RGB") for p in pair]
    except Exception:  # noqa: BLE001 - unreadable PNG: skip the image
        return None
    # Normalize to a common height; panels of the same view are normally
    # already identical in size.
    target_h = min(im.height for im in imgs)
    scaled = []
    for im in imgs:
        if im.height != target_h:
            w = round(im.width * target_h / im.height)
            im = im.resize((max(1, w), target_h), Image.LANCZOS)
        scaled.append(im)
    font = ImageFont.load_default()
    title_h, cap_h, gap, pad = 40, 26, 12, 10
    w1, w2 = scaled[0].width, scaled[1].width
    width = w1 + gap + w2
    height = title_h + cap_h + target_h
    canvas = Image.new("RGB", (width, height), (18, 18, 22))
    draw = ImageDraw.Draw(canvas)
    if diff.is_empty:
        title = f"diff {a_id} -> {b_id}: no differences"
    else:
        title = (
            f"diff {a_id} -> {b_id}: {_n(diff.total, 'change')} "
            f"({len(diff.added)} added, "
            f"{len(diff.removed)} removed, "
            f"{len(diff.changed)} replaced)"
        )
    draw.text((pad, (title_h - 14) // 2), title, font=font, fill=(235, 235, 240))
    for x, im, label, color in (
        (0, scaled[0], a_id, (255, 140, 140)),
        (w1 + gap, scaled[1], b_id, (140, 230, 150)),
    ):
        draw.text(
            (x + pad, title_h + (cap_h - 14) // 2),
            label, font=font, fill=color,
        )
        canvas.paste(im, (x, title_h + cap_h))
    draw.rectangle(
        [w1, title_h + cap_h, w1 + gap - 1, height - 1], fill=(70, 70, 80)
    )
    out_path = Path(out_path)
    canvas.save(out_path)
    return out_path
