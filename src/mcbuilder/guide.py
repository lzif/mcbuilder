"""Layer-by-layer build guide: what to place, layer by layer, for building by hand.

:func:`write_guide` turns a grid into a folder:

- ``layer-01.png`` … one top-down plan per Y layer (bottom first). Blocks
  of the current layer are drawn with their top texture; the layer below
  is shown faded so you can line things up. Markers show orientation:
  an arrow for ``facing``, a bar for ``axis=x/z``, a ``T`` for top-half
  stairs/slabs/trapdoors.
- ``guide.md`` — the full material list, then each layer's image and
  material list.

Coordinates in the guide are relative to the structure's north-west
bottom corner, the same origin a structure block / Litematica placement
uses: ``x`` grows east (right), ``z`` grows south (down), layer 1 is the
bottom.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mcbuilder.render import fast as _fast
from mcbuilder.voxels import AIR, UNSET

__all__ = ["item_counts", "write_guide"]

_BG = (246, 243, 236)
_GRID = (200, 194, 182)
_GRID_MAJOR = (150, 144, 132)
_INK = (40, 38, 34)
_MAX_GRID_PX = 1400
_LEGEND_W = 330


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without FreeType support
        return ImageFont.load_default()


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------

#: Second halves of two-cell blocks: not a separate item.
_SECOND_HALF = {("half", "upper"), ("part", "head")}


def _item_of(block: str) -> tuple[str, int] | None:
    """``(item_name, count)`` needed for one cell, or ``None`` (air, 2nd halves)."""
    name, props = _fast._split_blockstate(block)
    if name == AIR:
        return None
    if any((k, v) in _SECOND_HALF for k, v in props.items()):
        return None
    if props.get("type") == "double" and name.endswith("_slab"):
        return name, 2
    return name, 1


def item_counts(blocks) -> Counter:
    """Items needed to place ``blocks`` (an iterable of block strings)."""
    out: Counter = Counter()
    for b in blocks:
        item = _item_of(b)
        if item:
            out[item[0]] += item[1]
    return out


def _stacks(n: int) -> str:
    s, r = divmod(n, 64)
    if not s:
        return str(n)
    return f"{s}×64" + (f" + {r}" if r else "")


def _short(name: str) -> str:
    return name.split(":", 1)[1] if name.startswith("minecraft:") else name


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------

_ARROW = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def _marker(draw: ImageDraw.ImageDraw, x0: int, y0: int, c: int, props: dict) -> None:
    """Orientation marker for one cell (image coords, cell size ``c``)."""
    cx, cy = x0 + c / 2, y0 + c / 2
    facing = props.get("facing")
    if facing in _ARROW:
        dx, dy = _ARROW[facing]
        tip = (cx + dx * c * 0.36, cy + dy * c * 0.36)
        back = (cx - dx * c * 0.18, cy - dy * c * 0.18)
        px, py = -dy * c * 0.2, dx * c * 0.2
        tri = [tip, (back[0] + px, back[1] + py), (back[0] - px, back[1] - py)]
        draw.polygon(tri, fill=(255, 255, 255), outline=(0, 0, 0))
    elif facing in ("up", "down"):
        r = c * 0.14
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            fill=(255, 255, 255) if facing == "up" else (0, 0, 0),
            outline=(0, 0, 0) if facing == "up" else (255, 255, 255),
        )
    axis = props.get("axis")
    if axis in ("x", "z"):
        w = c * 0.36
        box = (
            (cx - w, cy - 1.5, cx + w, cy + 1.5)
            if axis == "x"
            else (cx - 1.5, cy - w, cx + 1.5, cy + w)
        )
        draw.rectangle(box, fill=(255, 255, 255), outline=(0, 0, 0))
    if props.get("half") == "top" or props.get("type") == "top":
        f = _font(max(8, int(c * 0.38)))
        draw.text(
            (x0 + 2, y0 + 1),
            "T",
            font=f,
            fill=(255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0),
        )


def _top_textures(palette, assets_root) -> dict[int, Image.Image]:
    out = {}
    for idx, block in enumerate(palette):
        if block == AIR:
            continue
        faces = _fast._build_face_textures(block, assets_root, set())
        img = faces.get("up") or faces.get("north")
        out[idx] = img.convert("RGB")
    return out


def _layer_image(arr, y: int, palette, textures, title: str) -> tuple[Image.Image, Counter]:
    sx, _, sz = arr.shape
    c = max(10, min(28, _MAX_GRID_PX // max(sx, sz)))
    top, left = 96, 44
    gw, gh = sx * c, sz * c
    width = max(left + gw + 20 + _LEGEND_W, 720)
    height = max(top + gh + 30, top + 40)
    layer = arr[:, y, :]
    below = arr[:, y - 1, :] if y > 0 else None
    counts = item_counts(palette[i] for i in layer.ravel() if i != UNSET)

    legend_rows = len(counts)
    height = max(height, top + 30 + legend_rows * 24 + 20)
    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)
    draw.text((left, 16), title, font=_font(22), fill=_INK)
    draw.text(
        (left, 46),
        "north is up  |  x: east (right)  |  z: south (down)  |  "
        "arrow: facing  |  T: top half  |  faded: layer below",
        font=_font(13),
        fill=(110, 104, 96),
    )

    tiles = {i: t.resize((c, c), Image.NEAREST) for i, t in textures.items()}
    ghosts = {i: Image.blend(t, Image.new("RGB", t.size, _BG), 0.75) for i, t in tiles.items()}

    for x in range(sx):
        for z in range(sz):
            px, pz = left + x * c, top + z * c
            idx = int(layer[x, z])
            if idx != UNSET and palette[idx] != AIR:
                img.paste(tiles[idx], (px, pz))
            elif (
                below is not None
                and int(below[x, z]) not in (UNSET,)
                and palette[int(below[x, z])] != AIR
            ):
                img.paste(ghosts[int(below[x, z])], (px, pz))
    for x in range(sx):
        for z in range(sz):
            idx = int(layer[x, z])
            if idx != UNSET and palette[idx] != AIR:
                _marker(
                    draw, left + x * c, top + z * c, c, _fast._split_blockstate(palette[idx])[1]
                )

    for i in range(sx + 1):
        col = _GRID_MAJOR if i % 5 == 0 else _GRID
        draw.line((left + i * c, top, left + i * c, top + gh), fill=col)
    for k in range(sz + 1):
        col = _GRID_MAJOR if k % 5 == 0 else _GRID
        draw.line((left, top + k * c, left + gw, top + k * c), fill=col)
    small = _font(11)
    for i in range(0, sx, 5):
        draw.text((left + i * c + 2, top - 14), str(i), font=small, fill=_INK)
    for k in range(0, sz, 5):
        draw.text((6, top + k * c + 2), str(k), font=small, fill=_INK)

    lx, ly = left + gw + 20, top
    draw.text((lx, ly - 24), "this layer", font=_font(14), fill=_INK)
    name_to_idx = {}
    for idx, block in enumerate(palette):
        name_to_idx.setdefault(_fast._split_blockstate(block)[0], idx)
    for name, n in counts.most_common():
        idx = name_to_idx.get(name)
        if idx in tiles:
            img.paste(tiles[idx].resize((18, 18), Image.NEAREST), (lx, ly))
        draw.text((lx + 26, ly + 2), f"{n:>4}  {_short(name)}", font=_font(13), fill=_INK)
        ly += 24
    return img, counts


# ---------------------------------------------------------------------------
# guide
# ---------------------------------------------------------------------------


def write_guide(
    grid, out_dir, assets_dir=None, *, title: str = "Build guide", cover: str | None = None
) -> Path:
    """Write the layer images and ``guide.md`` into ``out_dir``; returns the md path.

    ``cover`` is an optional image path (relative to ``out_dir``) shown at
    the top, e.g. a faithful iso preview.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    arr, palette, _ = grid.to_dense()
    arr = np.asarray(arr, dtype=np.int32)
    textures = _top_textures(palette, _fast._resolve_assets_root(assets_dir))

    solid = np.zeros(len(palette) + 1, dtype=bool)
    for i, b in enumerate(palette):
        solid[i] = b != AIR
    filled = solid[np.where(arr == UNSET, len(palette), arr)]
    layers = [y for y in range(arr.shape[1]) if filled[:, y, :].any()]

    total = item_counts(palette[i] for i in arr.ravel() if i != UNSET)
    sx, sy, sz = arr.shape
    md = [f"# {title}", ""]
    if cover:
        md += [f"![{title}]({cover})", ""]
    md += [
        f"Size: **{sx} × {sy} × {sz}** (x × y × z), "
        f"{len(layers)} layers, {sum(total.values())} items.",
        "",
        "Coordinates count from the north-west bottom corner: x to the "
        "east, z to the south, layer 1 at the bottom. In each plan the "
        "faded blocks are the layer below.",
        "",
        "## Materials",
        "",
        "| Item | Count | Stacks |",
        "|---|---:|---:|",
    ]
    md += [f"| {_short(n)} | {k} | {_stacks(k)} |" for n, k in total.most_common()]
    md.append("")

    for step, y in enumerate(layers, start=1):
        name = f"layer-{step:02d}.png"
        img, counts = _layer_image(
            arr, y, palette, textures, f"Layer {step} of {len(layers)}   (y = {y})"
        )
        img.save(out / name)
        md += [
            f"## Layer {step} (y = {y})",
            "",
            f"![Layer {step}]({name})",
            "",
            ", ".join(f"{k} {_short(n)}" for n, k in counts.most_common()),
            "",
        ]
    path = out / "guide.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path
