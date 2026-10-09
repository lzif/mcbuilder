"""Direction-trusted preview tier (PLAN §3).

The fast tier (``preview.py``) renders textured cubes and is flagged
``directions_untrusted`` — it cannot show facing/axis state, which the
v8 wrong-facing stair proved is load-bearing. This tier renders
*simplified per-block geometry that shows orientation truthfully*:

- stairs → oriented step/wedge shapes (facing × half × shape), built as
  polygon-projected boxes — the cost driver of this tier, not oriented
  cubes;
- slabs → half-height boxes (top/bottom/double);
- logs/pillars (``axis``) → full cube + contrasting axis band;
- walls/fences → centered posts (connections resolve in-game);
- every other block carrying ``facing`` → cube + facing plate
  (trapdoors render thin, per their ``half``);
- sign/banner ``rotation`` → cube + rotation arrow on the top face;
- any *other* directional block → labeled cube (magenta) **plus** one
  warning per block type (``untrusted_blocks`` in the result info) —
  untrusted-but-surfaced beats silent;
- everything else (no directional props) → plain flat-color cube.

Flat colors per block type (deterministic md5, same as the fast tier's
fallback); **no textures needed**. Slow and ugly is fine — truthful is
the requirement.

Rotation semantics are shared with the server-side paster: see
``mcbuilder.rotation`` (PLAN §3 normative table, mirrors
``StructurePaster.rotateBlockData``).
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mcbuilder import preview as _fast
from mcbuilder.views import View

__all__ = ["RenderResult", "render", "classify", "mesh_for_block"]

# Substrings marking a block as a log/pillar for axis handling (PLAN §3:
# axis boxes are scoped to "logs/pillars (axis)" — other axis blocks like
# chains fall through to the labeled-cube fallback).
_AXIS_LOG_HINTS = ("log", "wood", "stem", "hyphae", "pillar")

#: Props that make a block directional.
_DIRECTIONAL_PROPS = frozenset({"facing", "axis", "rotation"})

_PLATE_COLOR = (45, 45, 45)
_ARROW_COLOR = (235, 235, 235)
_FALLBACK_COLOR = (205, 70, 205)

# Classic isometric face shading, matching the fast tier's look.
_SHADES = {
    (0, 1, 0): 1.0,
    (0, -1, 0): 0.5,
    (0, 0, -1): 0.8,
    (0, 0, 1): 0.8,
    (1, 0, 0): 0.6,
    (-1, 0, 0): 0.6,
}


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def classify(name: str, props: dict[str, str]) -> str:
    """Return the trusted-tier rendering kind for a block.

    One of ``stairs`` | ``slab`` | ``axis`` | ``post`` | ``facing`` |
    ``rotation`` | ``fallback`` | ``cube``. See the module docstring for
    the handled set (PLAN §3).
    """
    short = name.split(":", 1)[-1]
    if short.endswith("_stairs"):
        return "stairs"
    if short.endswith("_slab"):
        return "slab"
    if "axis" in props and any(h in short for h in _AXIS_LOG_HINTS):
        return "axis"
    if short.endswith("_fence") or short.endswith("_wall"):
        return "post"
    if "facing" in props:
        return "facing"
    if "rotation" in props:
        return "rotation"
    if _DIRECTIONAL_PROPS & props.keys():
        return "fallback"
    return "cube"


# ---------------------------------------------------------------------------
# mesh construction (unit-cube-local coordinates)
# ---------------------------------------------------------------------------

# A polygon: (points, normal, color).
_Poly = tuple


def _box_quads(box, color) -> list:
    """Six quads of an axis-aligned box, with outward normals."""
    x0, y0, z0, x1, y1, z1 = box
    return [
        ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0), color),
        ([(x0, y0, z0), (x0, y0, z1), (x1, y0, z1), (x1, y0, z0)], (0, -1, 0), color),
        ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1), color),
        ([(x0, y0, z1), (x0, y1, z1), (x1, y1, z1), (x1, y0, z1)], (0, 0, 1), color),
        ([(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)], (1, 0, 0), color),
        ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], (-1, 0, 0), color),
    ]


def _rot_box_y_cw(box) -> tuple:
    """Rotate a unit-cube-local box 90° clockwise (north→east), viewed from above."""
    x0, y0, z0, x1, y1, z1 = box
    return (1.0 - z1, y0, x0, 1.0 - z0, y1, x1)


def _rot_box_y_180(box) -> tuple:
    x0, y0, z0, x1, y1, z1 = box
    return (1.0 - x1, y0, 1.0 - z1, 1.0 - x0, y1, 1.0 - z0)


def _mirror_box_y(box) -> tuple:
    """Mirror a box vertically (bottom↔top), for ``half=top`` stairs."""
    x0, y0, z0, x1, y1, z1 = box
    return (x0, 1.0 - y1, z0, x1, 1.0 - y0, z1)


# North-facing, bottom-half, straight stair template (tall part at back = +Z).
_STAIR_SLAB = (0.0, 0.0, 0.0, 1.0, 0.5, 1.0)
_STAIR_BACK = (0.0, 0.0, 0.5, 1.0, 1.0, 1.0)


def _stair_boxes(facing: str, half: str, shape: str) -> list[tuple]:
    """Unit-cube-local boxes for a stair blockstate.

    ``shape``: ``straight`` (default) | ``inner_left`` | ``inner_right``
    | ``outer_left`` | ``outer_right``. Inner/outer corners are the
    documented approximation: inner adds the front-side upper quarter,
    outer drops the back-side quarter (see module docstring — "slow and
    ugly", deterministic, pinned by tests).
    """
    boxes = [_STAIR_SLAB, _STAIR_BACK]
    if shape == "inner_left":
        boxes.append((0.0, 0.5, 0.0, 0.5, 1.0, 0.5))
    elif shape == "inner_right":
        boxes.append((0.5, 0.5, 0.0, 1.0, 1.0, 0.5))
    elif shape == "outer_left":
        boxes[1] = (0.5, 0.0, 0.5, 1.0, 1.0, 1.0)
    elif shape == "outer_right":
        boxes[1] = (0.0, 0.0, 0.5, 0.5, 1.0, 1.0)
    if half == "top":
        boxes = [_mirror_box_y(b) for b in boxes]
    # Rotate the north template to the requested facing.
    turns = {"north": 0, "east": 1, "south": 2, "west": 3}.get(facing, 0)
    for _ in range(turns):
        boxes = [_rot_box_y_cw(b) for b in boxes]
    return boxes


def _shade(color: tuple[int, int, int], normal: tuple) -> tuple[int, int, int]:
    factor = _SHADES.get(tuple(normal), 0.75)
    return tuple(min(255, int(c * factor)) for c in color)


def _facing_plate(facing: str) -> tuple:
    """Thin dark plate centered on the facing face (unit-cube-local)."""
    a, b = 0.30, 0.70
    t = 0.05
    if facing == "north":
        return (a, a, -t, b, b, t)
    if facing == "south":
        return (a, a, 1 - t, b, b, 1 + t)
    if facing == "east":
        return (1 - t, a, a, 1 + t, b, b)
    if facing == "west":
        return (-t, a, a, t, b, b)
    if facing == "up":
        return (a, 1 - t, a, b, 1 + t, b)
    return (a, -t, a, b, t, b)  # down (or anything unexpected)


def _rotation_arrow(rotation: int) -> list:
    """Flat triangle on the top face pointing at the sign/banner angle."""
    theta = math.radians((rotation % 16) * 22.5)
    # rotation=0 -> south; increasing rotation runs counterclockwise viewed
    # from above (4=west, 8=north, 12=east). This matches the PLAN §3 table:
    # CW90 adds +4 to rotation and maps south->west, so rotation=4 must
    # point west. (Getting this handedness wrong is exactly the bug class
    # the trusted tier exists to prevent.)
    dx, dz = -math.sin(theta), math.cos(theta)
    px, pz = math.cos(theta), math.sin(theta)
    cx, cz, y = 0.5, 0.5, 1.02
    tip = (cx + 0.38 * dx, y, cz + 0.38 * dz)
    b1 = (cx - 0.12 * dx + 0.14 * px, y, cz - 0.12 * dz + 0.14 * pz)
    b2 = (cx - 0.12 * dx - 0.14 * px, y, cz - 0.12 * dz - 0.14 * pz)
    return [([tip, b1, b2], (0, 1, 0), _ARROW_COLOR)]


def mesh_for_block(canonical: str) -> tuple[list, str | None]:
    """Build the trusted-tier mesh for one canonical block string.

    Returns ``(polys, label)`` where ``polys`` is a list of
    ``(points, normal, color)`` in unit-cube-local coordinates and
    ``label`` is a short block name for the fallback overlay (else None).
    """
    name, props = _fast._split_blockstate(canonical)
    kind = classify(name, props)
    base = _fast._fallback_color(name)
    polys: list = []
    label = None

    if kind == "stairs":
        for box in _stair_boxes(
            props.get("facing", "north"),
            props.get("half", "bottom"),
            props.get("shape", "straight"),
        ):
            polys.extend(_box_quads(box, base))
    elif kind == "slab":
        t = props.get("type", "bottom")
        box = (0.0, 0.0, 0.0, 1.0, 0.5, 1.0) if t == "bottom" else (
            (0.0, 0.5, 0.0, 1.0, 1.0, 1.0) if t == "top" else
            (0.0, 0.0, 0.0, 1.0, 1.0, 1.0))
        polys.extend(_box_quads(box, base))
    elif kind == "axis":
        polys.extend(_box_quads((0.0, 0.0, 0.0, 1.0, 1.0, 1.0), base))
        band_color = tuple(int(c * 0.55) for c in base)
        axis = props.get("axis", "y")
        band = {
            "x": (0.35, -0.03, -0.03, 0.65, 1.03, 1.03),
            "y": (-0.03, 0.35, -0.03, 1.03, 0.65, 1.03),
            "z": (-0.03, -0.03, 0.35, 1.03, 1.03, 0.65),
        }[axis]
        polys.extend(_box_quads(band, band_color))
    elif kind == "post":
        polys.extend(_box_quads((0.375, 0.0, 0.375, 0.625, 1.0, 0.625), base))
    elif kind == "facing":
        if "trapdoor" in name.split(":", 1)[-1]:
            # Trapdoors are thin: render the panel per half + facing plate.
            half = props.get("half", "bottom")
            panel = (0.0, 0.0, 0.0, 1.0, 0.1875, 1.0) if half == "bottom" else (
                (0.0, 0.8125, 0.0, 1.0, 1.0, 1.0))
            polys.extend(_box_quads(panel, base))
        else:
            polys.extend(_box_quads((0.0, 0.0, 0.0, 1.0, 1.0, 1.0), base))
        polys.extend(_box_quads(_facing_plate(props.get("facing", "north")),
                                _PLATE_COLOR))
    elif kind == "rotation":
        polys.extend(_box_quads((0.0, 0.0, 0.0, 1.0, 1.0, 1.0), base))
        try:
            rot = int(props.get("rotation", "0"))
        except ValueError:
            rot = 0
        polys.extend(_rotation_arrow(rot))
    elif kind == "fallback":
        polys.extend(_box_quads((0.0, 0.0, 0.0, 1.0, 1.0, 1.0), _FALLBACK_COLOR))
        label = name.split(":", 1)[-1]
    else:  # cube
        polys.extend(_box_quads((0.0, 0.0, 0.0, 1.0, 1.0, 1.0), base))
    return polys, label


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def _draw_trusted_badge(img: Image.Image) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default()
    text = "DIRECTIONS TRUSTED"
    lb = d.textbbox((0, 0), text, font=font)
    tw, th = lb[2] - lb[0], lb[3] - lb[1]
    pad = 5
    x, y = 10, 10
    d.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad],
                fill=(20, 90, 40, 200))
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def _render_view(arr, palette, crop, view, mesh_cache, labels) -> Image.Image:
    d, r, u = _fast._camera(view)
    (x0, x1), (y0, y1), (z0, z1) = crop

    corners = np.array([
        [x, y, z]
        for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)
    ], dtype=float)
    proj = _fast._project(corners, r, u)
    minx, miny = proj.min(axis=0)
    maxx, maxy = proj.max(axis=0)
    mx, my = _fast.MARGIN / 2 * (maxx - minx), _fast.MARGIN / 2 * (maxy - miny)
    minx -= mx
    maxx += mx
    miny -= my
    maxy += my
    w2d, h2d = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    scale = _fast.LONGEST_SIDE_PX / max(w2d, h2d)
    W, H = int(round(w2d * scale)), int(round(h2d * scale))

    def to_px(sx, sy):
        return (int(round((sx - minx) * scale)),
                int(round((maxy - sy) * scale)))

    canvas = Image.new("RGB", (W, H), _fast._BG)
    draw = ImageDraw.Draw(canvas)

    # Collect polygons: (depth, x, y, z, seq, points3d, normal, color).
    polys = []
    seq = 0
    sub = arr[x0:x1, y0:y1, z0:z1]
    cells = np.argwhere(_fast._renderable_mask(sub, palette))
    for cell in cells:
        lx, ly, lz = (int(v) for v in cell)
        idx = int(sub[lx, ly, lz])
        if idx < 0 or idx >= len(palette):
            continue
        block = palette[idx]
        if block == "minecraft:air":
            continue
        cached = mesh_cache.get(idx)
        if cached is None:
            cached = mesh_for_block(block)
            mesh_cache[idx] = cached
        mesh, label = cached
        x, y, z = lx + x0, ly + y0, lz + z0
        if label is not None:
            # Fallback blocks (and only they) carry a label.
            labels.append((x + 0.5, y + 0.5, z + 0.5, label))
        for points, normal, color in mesh:
            pts = [(px + x, py + y, pz + z) for px, py, pz in points]
            # Back-face culling: draw only faces turned toward the camera.
            if sum(n * dd for n, dd in zip(normal, d)) >= -1e-9:
                continue
            depth = float(sum(p[i] * d[i] for p in pts for i in range(3)) / len(pts))
            polys.append((depth, x, y, z, seq, pts, normal, color))
            seq += 1

    # Painter's algorithm, farthest first; seq keeps it deterministic.
    polys.sort(key=lambda t: (-t[0], t[1], t[2], t[3], t[4]))
    for _, _, _, _, _, pts, normal, color in polys:
        shaded = _shade(color, normal)
        px = [to_px(sx, sy) for sx, sy in _fast._project(np.array(pts), r, u)]
        draw.polygon(px, fill=shaded)

    # Fallback labels (2D overlay): one per block type per view. The label's
    # job is to name the magenta cubes; repeating it on every stacked cell
    # (e.g. a chain column) is unreadable spam.
    if labels:
        font = ImageFont.load_default()
        seen: set[str] = set()
        for fx, fy, fz, text in labels:
            if text in seen:
                continue
            seen.add(text)
            sx, sy = _fast._project(np.array([[fx, fy, fz]]), r, u)[0]
            lx, ly = to_px(sx, sy)
            draw.text((lx, ly), text, font=font, anchor="mm",
                      fill=(255, 255, 255, 255),
                      stroke_width=2, stroke_fill=(0, 0, 0, 255))

    _fast._overlay_label_and_compass(canvas, view, r, u)
    _draw_trusted_badge(canvas)
    return canvas


def render(grid, out_dir, views: list[View],
           assets_dir=None) -> _fast.RenderResult:
    """Render each view with the direction-trusted tier. Returns ordered paths.

    ``assets_dir`` is accepted for signature parity with the fast tier and
    ignored — this tier needs no textures. Filenames encode the camera
    (``view.label + ".png"``). The returned ``RenderResult.info`` carries
    ``untrusted_blocks`` (``{block_name: cell_count}`` for blocks rendered
    as labeled cubes) so the caller can surface the per-type warnings
    PLAN §3 requires.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    arr, palette, _provenance = grid.to_dense()
    arr = np.asarray(arr, dtype=np.int32)
    crop = _fast._crop_bounds(arr, palette)

    mesh_cache: dict = {}
    untrusted: dict[str, int] = {}
    kinds: dict[int, str] = {}
    if crop is not None:
        # Classify each palette entry once; count fallback cells once per
        # build (not per view) for the PLAN §3 per-type warnings.
        for idx, block in enumerate(palette):
            if block == "minecraft:air":
                continue
            name, props = _fast._split_blockstate(block)
            kind = classify(name, props)
            kinds[idx] = kind
            if kind == "fallback":
                untrusted[name] = untrusted.get(name, 0) + int((arr == idx).sum())
    paths: list[Path] = []

    for view in views:
        if crop is None:
            img = Image.new("RGB", (512, 512), _fast._BG)
            d, r, u = _fast._camera(view)
            _fast._overlay_label_and_compass(img, view, r, u)
            _draw_trusted_badge(img)
        else:
            img = _render_view(arr, palette, crop, view, mesh_cache, [])
        path = out / f"{view.label}.png"
        img.save(path)
        paths.append(path)

    info = {
        # This tier needs no assets (flat colors, no textures); the key
        # exists for RenderResult shape parity with the fast tier.
        "assets_missing": False,
        "assets_root": None,
        "fallback_blocks": [],
        "untrusted_blocks": dict(sorted(untrusted.items())),
        "views": len(views),
    }
    return _fast.RenderResult(paths, info)


RenderResult = _fast.RenderResult

__all__ = ["RenderResult", "render", "classify", "mesh_for_block"]
