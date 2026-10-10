"""Fast-tier preview renderer (PLAN rev 7, section 3).

Isometric orthographic renderer: flat vanilla textures on cubes, painter's
algorithm, back-to-front along the view direction. Deterministic — same
build + same views => pixel-identical PNGs, every run.

Grid duck-type contract (implemented by mcbuilder.voxels.VoxelGrid):

- ``grid.to_dense()`` -> ``(arr, palette, provenance)`` where ``arr`` is a
  numpy int32 array of shape ``(nx, ny, nz)`` indexed ``[x, y, z]`` holding
  palette indices, pre-cropped to the placed-cell bbox (explicit
  ``"minecraft:air"`` expands the bounds like any placed cell — see
  ``VoxelGrid.to_dense``; ``arr[i, j, k]`` is the cell at
  ``(minx + i, miny + j, minz + k)``). ``palette`` is a list mapping
  index -> canonical blockstate string; never-placed cells inside the bbox
  read as ``-1`` (UNSET) and are skipped by the renderer, as are cells whose
  palette entry is exactly ``"minecraft:air"`` (carved air). ``provenance``
  is opaque.
- ``grid.bounds()`` is not consumed by the renderer: because ``to_dense()``
  is pre-cropped, the render crop is derived from the array's renderable
  cells directly (array-relative, exclusive hi ends).

Texture rule (PLAN rev 7, section 3): per model parent type, from the first
variant's model (fallback ``all``):
``cube_all`` -> ``all`` on every face; ``cube_column`` -> ``end`` on
top/bottom, ``side`` on sides; ``cube`` and anything else -> six-face
lookup (top/bottom/side). If assets are missing or unreadable, blocks fall
back to a deterministic hash-based flat color — never a crash. Fallbacks
are reported in the returned info (``.info["fallback_blocks"]``) so the
caller can surface them as report.json warnings.

Fast-tier honesty: every preview carries ``directions_untrusted=true`` in
report.json (set by the caller, see report.view_entry) because the fast
tier cannot show facing/connection state.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .views import View

#: Longest image side in pixels (pinned framing rule).
LONGEST_SIDE_PX = 1024
#: Margin added around the projected bbox, as a fraction of each axis range.
MARGIN = 0.10

# Cube template parents with dedicated texture rules (PLAN rev 7, section 3).
# Anything else uses the six-face lookup.
_TEMPLATE_PARENTS = frozenset({"cube_all", "cube_column", "cube", "cube_mirrored"})

_BG = (30, 30, 38)

# Flat per-face shade multipliers (classic isometric shading).
_SHADES = {
    "up": 1.0,
    "down": 0.5,
    "north": 0.8,
    "south": 0.8,
    "east": 0.6,
    "west": 0.6,
}

# (face name, outward normal, 4 corner offsets in cyclic order).
_FACES = (
    ("up", (0, 1, 0), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1))),
    ("down", (0, -1, 0), ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0))),
    ("north", (0, 0, -1), ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))),
    ("south", (0, 0, 1), ((1, 0, 1), (1, 1, 1), (0, 1, 1), (0, 0, 1))),
    ("east", (1, 0, 0), ((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1))),
    ("west", (-1, 0, 0), ((0, 0, 1), (0, 1, 1), (0, 1, 0), (0, 0, 0))),
)


class RenderResult(list):
    """``list[Path]`` of rendered PNGs (in view order) plus ``.info``.

    ``info`` keys: ``assets_missing`` (bool), ``assets_root`` (str|None),
    ``fallback_blocks`` (sorted list of block names rendered with fallback
    colors), ``views`` (int).
    """

    def __init__(self, paths: list[Path], info: dict):
        super().__init__(paths)
        self.info = info


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

def _camera(view: View):
    """Return (d, r, u): view direction, screen-right, screen-up (unit)."""
    th = math.radians(view.azimuth)
    ph = math.radians(view.elevation)
    d = np.array([
        -math.sin(th) * math.cos(ph),
        -math.sin(ph),
        math.cos(th) * math.cos(ph),
    ])
    if abs(d[1]) > 0.999:
        # Looking straight up/down: screen-right = +X, screen-up = north.
        r = np.array([1.0, 0.0, 0.0])
    else:
        r = np.cross(d, np.array([0.0, 1.0, 0.0]))
        r = r / np.linalg.norm(r)
    u = np.cross(r, d)
    return d, r, u


def _project(points: np.ndarray, r: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Orthographic projection of (N,3) points to (N,2) screen coords."""
    return np.stack([points @ r, points @ u], axis=1)


# ---------------------------------------------------------------------------
# Assets: blockstates -> model chain -> per-face textures
# ---------------------------------------------------------------------------

def _resolve_assets_root(assets_dir) -> Path | None:
    """Find <root>/assets/minecraft under assets_dir.

    Accepts either the version dir itself (``.../<version>/``) or its
    parent (``.../``); with several versions present the first in sorted
    order wins (deterministic). Returns None when nothing is found.
    """
    if assets_dir is None:
        return None
    base = Path(assets_dir)
    direct = base / "client" / "assets" / "minecraft"
    if direct.is_dir():
        return direct
    if base.is_dir():
        for child in sorted(base.iterdir()):
            cand = child / "client" / "assets" / "minecraft"
            if cand.is_dir():
                return cand
    return None


def _split_blockstate(canonical: str) -> tuple[str, dict[str, str]]:
    """'minecraft:oak_log[axis=y]' -> ('minecraft:oak_log', {'axis': 'y'}).

    Any trailing NBT (``{...}``) is ignored for texture lookup.
    """
    head = canonical.split("{", 1)[0]
    if "[" in head:
        name, _, props = head.partition("[")
        props = props.rstrip("]")
        prop_dict = dict(p.split("=", 1) for p in props.split(",") if "=" in p)
    else:
        name, prop_dict = head, {}
    return name, prop_dict


# Default props for variant matching when the canonical blockstate omits
# them. Shared with the faithful tier: a missing prop means the vanilla
# default blockstate, which is also what the validator accepts and what
# structure-loading fills in. Without these, bare names like
# ``minecraft:oak_log`` (no ``axis``) match no variant in real vanilla
# blockstates (which, unlike some test fixtures, ship no empty-key
# default) and degrade to the flat fallback color.
_DEFAULT_PROPS = {
    "facing": "north",
    "half": "bottom",
    "shape": "straight",
    "type": "bottom",  # slabs
    "axis": "y",
    "hanging": "false",  # lanterns
    "waterlogged": "false",
    "open": "false",
}


def _match_variant(variants: dict, props: dict[str, str]):
    """Pick the most specific variant whose key pairs are all satisfied."""
    best, best_n = None, -1
    for key, value in variants.items():
        pairs = [p for p in key.split(",") if p] if key else []
        ok = True
        for p in pairs:
            k, _, v = p.partition("=")
            if props.get(k) != v:
                ok = False
                break
        if ok and len(pairs) > best_n:
            best, best_n = value, len(pairs)
    if isinstance(best, list):
        best = best[0] if best else None
    return best if isinstance(best, dict) else None


def _resolve_model_textures(block_name: str, props: dict, root: Path):
    """Return (textures, parent_leaf).

    textures maps texture variable -> PIL RGB image (None if unloadable);
    parent_leaf is the first known cube-template leaf walking down from the
    variant's model (e.g. 'cube_all', 'cube_column'), or None.
    Never raises: any failure yields ({}, None).
    """
    try:
        return _do_resolve(block_name, props, root)
    except Exception:
        return {}, None


def _do_resolve(block_name: str, props: dict, root: Path):
    short = block_name.split(":", 1)[-1]
    try:
        with open(root / "blockstates" / f"{short}.json",
                  encoding="utf-8") as f:
            bs = json.load(f)
    except Exception:
        return {}, None

    model_ref = None
    variants = bs.get("variants")
    if variants:
        # Fill missing props from vanilla defaults so partial canonical
        # blockstates (e.g. stairs without ``shape``, logs without ``axis``)
        # still match a variant — same convention as the faithful tier.
        full_props = dict(_DEFAULT_PROPS)
        full_props.update(props)
        var = _match_variant(variants, full_props)
        if var:
            model_ref = var.get("model")
    elif bs.get("multipart"):
        for case in bs["multipart"]:
            apply = case.get("apply")
            if isinstance(apply, list):
                apply = apply[0] if apply else None
            if isinstance(apply, dict) and apply.get("model"):
                model_ref = apply["model"]
                break

    if not model_ref:
        return {}, None

    # Walk the parent chain, collecting textures (child overrides parent).
    # A missing/unreadable parent just ends the walk; we keep what we have.
    chain: list[dict] = []
    seen = set()
    ref = model_ref
    for _ in range(8):
        rel = ref.split(":", 1)[-1]
        if rel in seen:
            break
        seen.add(rel)
        try:
            with open(root / "models" / f"{rel}.json",
                      encoding="utf-8") as f:
                model = json.load(f)
        except Exception:
            break
        chain.append(model)
        parent = model.get("parent")
        if not parent:
            break
        ref = parent

    if not chain:
        return {}, None

    textures: dict[str, str] = {}
    for model in reversed(chain):
        textures.update(model.get("textures", {}))

    # Resolve "#" variable references.
    def resolve(value: str, depth: int = 0) -> str | None:
        if not value.startswith("#") or depth > 8:
            return value
        return resolve(textures.get(value[1:], ""), depth + 1)

    # The template parent is the first known template leaf walking down from
    # the variant's model (e.g. cube_all for stone, cube_column for oak_log).
    leaves = []
    ref = model_ref
    for model in chain:
        leaves.append(ref.split(":", 1)[-1].split("/")[-1])
        ref = model.get("parent") or ""
    parent_leaf = next((l for l in leaves if l in _TEMPLATE_PARENTS), None)

    images: dict[str, Image.Image | None] = {}
    for var, value in textures.items():
        target = resolve(value)
        if not target:
            images[var] = None
            continue
        rel = target.split(":", 1)[-1]
        tex_path = root / "textures" / f"{rel}.png"
        try:
            with Image.open(tex_path) as im:
                images[var] = im.convert("RGB")
        except Exception:
            images[var] = None
    return images, parent_leaf


def _face_tex_vars(images: dict, parent_leaf: str | None) -> dict[str, str | None]:
    """Map each cube face -> texture variable name, per the parent-type rule."""
    keys = {k for k, v in images.items() if v is not None}
    if parent_leaf == "cube_all":
        var = "all" if "all" in keys else None
        return {face: var for face, _, _ in _FACES}
    if parent_leaf == "cube_column":
        end = "end" if "end" in keys else None
        side = "side" if "side" in keys else None
        return {
            "up": end, "down": end,
            "north": side, "south": side, "east": side, "west": side,
        }

    def pick(*cands: str) -> str | None:
        return next((c for c in cands if c in keys), None)

    # Last resort for non-cube models (fences, torches, ...): any usable
    # texture var beats a flat fallback color in this tier.
    any_tex = next((k for k in keys if k != "particle"), None)
    side = pick("side", "front", "all", "texture") or any_tex
    return {
        "up": pick("top", "up", "end", "all", "texture") or side,
        "down": pick("bottom", "down", "end", "all", "texture") or side,
        "north": side, "south": side, "east": side, "west": side,
    }


def _fallback_color(block_name: str) -> tuple[int, int, int]:
    """Deterministic flat color per block name (md5, NOT builtin hash)."""
    digest = hashlib.md5(block_name.encode("utf-8")).digest()
    return (digest[0], digest[1], digest[2])


def _shade(img: Image.Image, factor: float) -> Image.Image:
    if factor >= 1.0:
        return img
    return img.point(lambda v: min(255, int(v * factor)))


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _order_quad(corners: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Order 4 convex-quad corners as NW, SW, SE, NE (screen space, y down)."""
    by_y = sorted(corners, key=lambda p: (p[1], p[0]))
    top, bottom = by_y[:2], by_y[2:]
    nw, ne = sorted(top, key=lambda p: p[0])
    sw, se = sorted(bottom, key=lambda p: p[0])
    return [nw, sw, se, ne]


def _draw_face(canvas: Image.Image, corners_px, tex: Image.Image) -> None:
    """Paste a shaded texture across a projected face parallelogram."""
    xs = [p[0] for p in corners_px]
    ys = [p[1] for p in corners_px]
    x0, x1 = math.floor(min(xs)), math.ceil(max(xs))
    y0, y1 = math.floor(min(ys)), math.ceil(max(ys))
    bw, bh = x1 - x0, y1 - y0
    if bw < 1 or bh < 1:
        return
    # QUAD data maps output corners (NW, SW, SE, NE) to input coords.
    nw, sw, se, ne = _order_quad(corners_px)
    tw, th = tex.size
    warped = tex.transform(
        (bw, bh), Image.QUAD,
        (0, 0, 0, th, tw, th, tw, 0),
        Image.NEAREST,
    )
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon(
        [(x - x0, y - y0) for x, y in (nw, sw, se, ne)], fill=255
    )
    canvas.paste(warped, (x0, y0), mask)


def _overlay_label_and_compass(img: Image.Image, view: View,
                               r: np.ndarray, u: np.ndarray) -> None:
    """Draw the view label (bottom-left) and a north compass (bottom-right)."""
    d = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default()
    W, H = img.size
    pad = 5

    # Label.
    lb = d.textbbox((0, 0), view.label, font=font)
    tw, th = lb[2] - lb[0], lb[3] - lb[1]
    lx, ly = 10, H - 10 - th - 2 * pad
    d.rectangle([lx - pad, ly - pad, lx + tw + pad, ly + th + pad],
                fill=(0, 0, 0, 160))
    d.text((lx, ly), view.label, font=font, fill=(255, 255, 255, 255))

    # Compass: project north (-Z) onto the screen.
    north = np.array([0.0, 0.0, -1.0])
    sx, sy = float(north @ r), float(north @ u)
    cx, cy, rad = W - 42, H - 42, 24
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
              outline=(255, 255, 255, 220), width=2)
    length = math.hypot(sx, sy)
    if length > 1e-6:
        dx, dy = sx / length, -sy / length  # screen y points down
        ex, ey = cx + dx * (rad - 6), cy + dy * (rad - 6)
        d.line([cx, cy, ex, ey], fill=(255, 255, 255, 230), width=2)
        nb = d.textbbox((0, 0), "N", font=font)
        d.text((ex + dx * 10 - (nb[2] - nb[0]) / 2,
                ey + dy * 10 - (nb[3] - nb[1]) / 2),
               "N", font=font, fill=(255, 255, 255, 255))
    else:
        # Degenerate (camera looking straight along the north axis): letter only.
        nb = d.textbbox((0, 0), "N", font=font)
        d.text((cx - (nb[2] - nb[0]) / 2, cy - (nb[3] - nb[1]) / 2),
               "N", font=font, fill=(255, 255, 255, 255))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def _renderable_mask(arr: np.ndarray, palette: list) -> np.ndarray:
    """Boolean mask of cells that should actually be drawn.

    Never-placed cells (``-1``/UNSET) and carved ``minecraft:air`` cells are
    excluded; everything else (any palette index >= 0) is renderable. Note
    air's palette index is *not* assumed to be 0 — it is wherever the grid
    interned it.
    """
    try:
        air_idx = palette.index("minecraft:air")
    except ValueError:
        air_idx = None
    if air_idx is None:
        return arr >= 0
    return (arr >= 0) & (arr != air_idx)


def _crop_bounds(arr: np.ndarray, palette: list) -> tuple[tuple[int, int], ...] | None:
    """Tight array-relative crop (exclusive hi ends) over renderable cells.

    ``VoxelGrid.to_dense()`` already pre-crops to the placed-cell bbox, so this
    is normally the full array extent; it is recomputed here (rather than
    trusting ``grid.bounds()``) so duck-typed grids with non-cropped arrays
    also frame correctly. Returns ``None`` when nothing is renderable (the
    caller draws the empty-grid placeholder).
    """
    occ = np.argwhere(_renderable_mask(arr, palette))
    if len(occ) == 0:
        return None
    lo = occ.min(axis=0)
    hi = occ.max(axis=0) + 1
    return ((int(lo[0]), int(hi[0])), (int(lo[1]), int(hi[1])),
            (int(lo[2]), int(hi[2])))


def _render_view(arr, palette, crop, view, tex_cache, fallback_blocks,
                 assets_root) -> Image.Image:
    d, r, u = _camera(view)
    (x0, x1), (y0, y1), (z0, z1) = crop

    # Framing: project the 8 bbox corners (+10% margin), fit, orthographic.
    corners = np.array([
        [x, y, z]
        for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)
    ], dtype=float)
    proj = _project(corners, r, u)
    minx, miny = proj.min(axis=0)
    maxx, maxy = proj.max(axis=0)
    mx, my = MARGIN / 2 * (maxx - minx), MARGIN / 2 * (maxy - miny)
    minx -= mx
    maxx += mx
    miny -= my
    maxy += my
    w2d, h2d = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    scale = LONGEST_SIDE_PX / max(w2d, h2d)
    W, H = int(round(w2d * scale)), int(round(h2d * scale))

    def to_px(sx, sy):
        return (int(round((sx - minx) * scale)),
                int(round((maxy - sy) * scale)))

    canvas = Image.new("RGB", (W, H), _BG)

    # Occupied cells, farthest first along the view direction.
    sub = arr[x0:x1, y0:y1, z0:z1]
    cells = np.argwhere(_renderable_mask(sub, palette))
    depths = (cells.astype(float) + np.array([x0, y0, z0])) @ d
    order = np.lexsort((cells[:, 2], cells[:, 1], cells[:, 0], -depths))

    for ci in order:
        lx, ly, lz = (int(v) for v in cells[ci])
        x, y, z = lx + x0, ly + y0, lz + z0
        idx = int(sub[lx, ly, lz])
        if idx < 0 or idx >= len(palette):
            continue  # never-placed cell inside the bbox
        block = palette[idx]
        if block == "minecraft:air":
            continue  # carved air renders as nothing

        face_tex = tex_cache.get(idx)
        if face_tex is None:
            face_tex = _build_face_textures(block, assets_root, fallback_blocks)
            tex_cache[idx] = face_tex

        # Visible faces, farthest first.
        visible = []
        for name, normal, offsets in _FACES:
            if sum(n * dd for n, dd in zip(normal, d)) < -1e-9:
                pts = np.array(
                    [[x + ox, y + oy, z + oz] for ox, oy, oz in offsets],
                    dtype=float,
                )
                visible.append((float(pts.mean(axis=0) @ d), name, pts))
        visible.sort(key=lambda t: -t[0])
        for _, name, pts in visible:
            tex = face_tex[name]
            if tex is None:
                continue
            corners_px = [to_px(sx, sy) for sx, sy in _project(pts, r, u)]
            _draw_face(canvas, corners_px, _shade(tex, _SHADES[name]))

    _overlay_label_and_compass(canvas, view, r, u)
    return canvas


def _build_face_textures(block: str, assets_root,
                         fallback_blocks: set) -> dict[str, Image.Image | None]:
    """Per-face PIL textures for one palette entry (with fallback colors)."""
    name, props = _split_blockstate(block)
    images, parent_leaf = ({}, None)
    if assets_root is not None:
        images, parent_leaf = _resolve_model_textures(name, props, assets_root)
    face_vars = _face_tex_vars(images, parent_leaf)
    out: dict[str, Image.Image | None] = {}
    for face, _, _ in _FACES:
        var = face_vars.get(face)
        img = images.get(var) if var else None
        if img is None:
            fallback_blocks.add(name)
            img = Image.new("RGB", (16, 16), _fallback_color(name))
        out[face] = img
    return out


def render(grid, out_dir: str | Path, views: list[View],
           assets_dir: str | Path | None) -> list[Path]:
    """Render each view to a PNG in out_dir. Returns ordered paths.

    Filenames encode the camera (``view.label + ".png"``). The returned
    list is a RenderResult carrying ``.info`` (asset fallback notes).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    arr, palette, _provenance = grid.to_dense()
    arr = np.asarray(arr, dtype=np.int32)
    crop = _crop_bounds(arr, palette)
    assets_root = _resolve_assets_root(assets_dir)

    tex_cache: dict[int, dict] = {}
    fallback_blocks: set[str] = set()
    paths: list[Path] = []

    for view in views:
        if crop is None:
            img = Image.new("RGB", (512, 512), _BG)
            d, r, u = _camera(view)
            _overlay_label_and_compass(img, view, r, u)
        else:
            img = _render_view(arr, palette, crop, view, tex_cache,
                               fallback_blocks, assets_root)
        path = out / f"{view.label}.png"
        img.save(path)
        paths.append(path)

    info = {
        "assets_missing": assets_root is None,
        "assets_root": str(assets_root) if assets_root else None,
        "fallback_blocks": sorted(fallback_blocks),
        "views": len(views),
    }
    return RenderResult(paths, info)


__all__ = ["LONGEST_SIDE_PX", "MARGIN", "RenderResult", "render"]
