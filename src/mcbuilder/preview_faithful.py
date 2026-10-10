"""Faithful preview tier (PLAN §3, v0.3).

Textured AND direction-truthful: each blockstate is resolved through the
vanilla client assets (blockstate JSON → model JSON → textures) and the
REAL model cuboids (``from``/``to`` boxes) are projected as textured
quads — no simplified stand-ins (Luki, 2026-10-09: "size dan shape block
juga harus match real Minecraft"). Stairs get the true multi-box stair
profile, walls the real post+arms, lanterns/chains/trapdoors their real
shapes, because the geometry comes straight from the model JSONs.

Orientation model (verified against the vanilla assets, 2026-10-09):

- Blockstate ``y`` rotations run CLOCKWISE viewed from above
  (``oak_stairs`` base model has its tall element at +X and maps to
  ``facing=east``; ``facing=south`` uses ``y=90``, which must carry
  +X→+Z).
- Blockstate ``x`` rotations use the right-hand rule about +X
  (``half=top`` stairs use ``x=180``: ``(y,z)→(1-y,1-z)``).
- When both are present, X applies first, then Y (verified: a
  south-facing top-half stair lands tall-at-south, top-half).
- ``facing`` for stairs = the direction of the tall part (same source).

``uvlock``: UVs are always assigned painted-on in MODEL space (the only
density-preserving behavior — a naive world-fixed assignment breaks
texel density on rotated non-square faces, which vanilla cannot do).
When uvlock is true, side faces additionally get v0 pinned to the top so
the texture stays upright instead of rotating with the model (this is
what keeps top-half stair side textures from rendering upside-down).
Painted-on assignment happens in MODEL space — corners are ordered by
the face's own UV axes *before* element/model rotations carry them
along. (Assigning after rotation spun textures 90° on any model with
x/y rotation — the tilted stone-brick courses Luki spotted 2026-10-09
— and degenerated for side faces turned 90°, where the sort axis is
constant.)

Determinism rules (documented, pinned by tests):

- Variant selection: most-specific match wins (ties → first in file
  order); a weighted variant list (``"apply": [...]`` / list value)
  always takes the FIRST entry — same rule as the fast tier.
- Multipart: every case whose ``when`` matches contributes its model,
  in file order. ``when`` supports ``{"prop": "value"}`` (AND),
  ``{"OR": [...]}`` and ``{"AND": [...]}``, nested.
- Missing blockstate / model / elements → labeled magenta cube plus
  one warning per block type in ``info["untrusted_blocks"]`` (same
  fallback rule as the trusted tier). A missing individual texture
  degrades that face to a flat deterministic color (reported in
  ``info["fallback_blocks"]``, like the fast tier) — the block still
  renders.

Two output modes:

- ``presentation=True`` (default): the Shadow Court look (Luki,
  2026-10-09) — clean light background, soft contact shadow, Minecraft
  per-face shading, high resolution, anti-aliased, title, NO badges /
  compass / view labels / debug overlays.
- ``presentation=False``: debug view — dark background, "FAITHFUL"
  badge, compass, view label (same chrome as the trusted tier).

Performance: per-palette-entry quad cache (geometry + cropped/shaded
textures resolved once); per-texture PIL image cache (no atlas — the
unique-texture count is small); painter's algorithm like the other
tiers. Fast enough for 7×7×7 waystones now and windmill-scale next.

Known quirk (documented, not a bug): stair rows (e.g. from
``roof_gable``/``stairs_run``) leave real 0.5-block see-through notches
between rows — vanilla Minecraft geometry, verified against the model
JSONs. From a high isometric angle the renderer shows through these
notches to whatever is below (background if floating). The trusted
tier renders the identical notches; the voxels are correct.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from mcbuilder import preview as _fast
from mcbuilder.views import View

__all__ = ["RenderResult", "render", "resolve_block_quads"]

# ---------------------------------------------------------------------------
# presentation constants (Shadow Court reference)
# ---------------------------------------------------------------------------

_BG_PRESENTATION = (244, 241, 235)
_BG_DEBUG = (30, 30, 38)
_TITLE_COLOR = (110, 105, 95)
_FALLBACK_MAGENTA = (205, 70, 205)

#: Output longest side (px) for presentation renders.
PRESENTATION_LONGEST_PX = 2048
#: Supersample factor (rendered at SS×, downscaled with LANCZOS).
SUPERSAMPLE = 2
#: Framing margin for presentation (generous, like the reference).
PRESENTATION_MARGIN = 0.35

# Classic Minecraft-ish face shading (matches the other tiers).
_SHADES = {
    (0, 1, 0): 1.0,
    (0, -1, 0): 0.5,
    (0, 0, -1): 0.8,
    (0, 0, 1): 0.8,
    (1, 0, 0): 0.6,
    (-1, 0, 0): 0.6,
}

_FACE_NORMALS = {
    "up": (0, 1, 0),
    "down": (0, -1, 0),
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "west": (-1, 0, 0),
    "east": (1, 0, 0),
}

# UV corner assignment per face direction: (u_axis, u_at_min, v_axis,
# v_at_min). u0 is the rect's left, v0 its top. Chosen so textures appear
# upright and unmirrored viewed from outside the face.
_UV_AXES = {
    # face: (u_axis, u_min_is_u0, v_axis, v_min_is_v0)
    "north": (0, False, 1, False),  # u→-x, v0 at top
    "south": (0, True, 1, False),   # u→+x, v0 at top
    "west": (2, True, 1, False),    # u→+z, v0 at top
    "east": (2, False, 1, False),   # u→-z, v0 at top
    "up": (0, True, 2, True),       # u→+x, v→+z (v0 at north)
    "down": (0, False, 2, True),    # u→-x, v→+z
}

_FACE_NAMES = ("up", "down", "north", "south", "west", "east")


# ---------------------------------------------------------------------------
# 3D rotation helpers (block-local 0–1 coords)
# ---------------------------------------------------------------------------

def _rot_y(p, degrees):
    """Vanilla blockstate Y rotation: clockwise viewed from above."""
    x, y, z = p
    for _ in range((degrees // 90) % 4):
        x, y, z = 1.0 - z, y, x
    return (x, y, z)


def _rot_y_dir(v, degrees):
    x, y, z = v
    for _ in range((degrees // 90) % 4):
        x, y, z = -z, y, x
    return (x, y, z)


def _rot_x(p, degrees):
    """Vanilla blockstate X rotation: right-hand rule about +X."""
    x, y, z = p
    for _ in range((degrees // 90) % 4):
        x, y, z = x, 1.0 - z, y
    return (x, y, z)


def _rot_x_dir(v, degrees):
    x, y, z = v
    for _ in range((degrees // 90) % 4):
        x, y, z = x, -z, y
    return (x, y, z)


def _apply_model_rotation(p, x_deg, y_deg):
    """X first, then Y (vanilla order, verified 2026-10-09)."""
    return _rot_y(_rot_x(p, x_deg), y_deg)


def _apply_model_rotation_dir(v, x_deg, y_deg):
    return _rot_y_dir(_rot_x_dir(v, x_deg), y_deg)


def _apply_element_rotation(p, origin, axis, angle_deg):
    """Rodrigues rotation of point p about axis through origin."""
    ox, oy, oz = (c / 16.0 for c in origin)
    theta = math.radians(angle_deg)
    c, s = math.cos(theta), math.sin(theta)
    k = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0),
         "z": (0.0, 0.0, 1.0)}[axis]
    vx, vy, vz = p[0] - ox, p[1] - oy, p[2] - oz
    # k × v
    cx = k[1] * vz - k[2] * vy
    cy = k[2] * vx - k[0] * vz
    cz = k[0] * vy - k[1] * vx
    dot = k[0] * vx + k[1] * vy + k[2] * vz
    rx = vx * c + cx * s + k[0] * dot * (1 - c)
    ry = vy * c + cy * s + k[1] * dot * (1 - c)
    rz = vz * c + cz * s + k[2] * dot * (1 - c)
    return (rx + ox, ry + oy, rz + oz)


# ---------------------------------------------------------------------------
# asset loading
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_texture_image(root: Path, rel: str, cache: dict):
    """PIL RGB image for a texture path (cached). None when unloadable.

    Animated textures (``.mcmeta`` with an ``animation`` section, e.g.
    lantern/soul_lantern in 26.2) are cropped to the FIRST frame:
    vanilla maps model UVs (0–16) to a single frame, not the full
    vertically-stacked strip. Without this, UVs get stretched over all
    frames and sample the wrong (usually darker) texels.
    """
    if rel in cache:
        return cache[rel]
    try:
        with Image.open(root / "textures" / f"{rel}.png") as im:
            img = im.convert("RGB")
        mcmeta = root / "textures" / f"{rel}.png.mcmeta"
        if mcmeta.is_file():
            try:
                meta = json.loads(mcmeta.read_text(encoding="utf-8"))
            except Exception:
                meta = None
            if isinstance(meta, dict) and isinstance(meta.get("animation"), dict):
                w, h = img.size
                if h > w and h % w == 0:
                    img = img.crop((0, 0, w, w))
    except Exception:
        img = None
    cache[rel] = img
    return img


def _resolve_model_elements_and_textures(model_ref: str, root: Path,
                                        tex_cache: dict):
    """Return (elements, images) or (None, None).

    Walks the parent chain (cycle-safe, depth 8): textures merge with
    child overriding parent; elements come from the nearest chain entry
    that defines them (vanilla inheritance — not merged).
    """
    chain = []
    seen = set()
    ref = model_ref
    for _ in range(8):
        rel = ref.split(":", 1)[-1]
        if rel in seen:
            break
        seen.add(rel)
        model = _read_json(root / "models" / f"{rel}.json")
        if model is None:
            break
        chain.append(model)
        parent = model.get("parent")
        if not parent:
            break
        ref = parent
    if not chain:
        return None, None
    elements = None
    for model in chain:
        if model.get("elements"):
            elements = model["elements"]
            break
    if not elements:
        return None, None
    textures: dict[str, str] = {}
    for model in reversed(chain):
        textures.update(model.get("textures", {}))

    def resolve(value: str, depth: int = 0):
        if not value.startswith("#") or depth > 8:
            return value
        return resolve(textures.get(value[1:], ""), depth + 1)

    images: dict[str, Image.Image | None] = {}
    for var, value in textures.items():
        target = resolve(value)
        if not target:
            images[var] = None
            continue
        images[var] = _load_texture_image(
            root, target.split(":", 1)[-1], tex_cache)
    return elements, images


def _when_matches(when, props: dict[str, str]) -> bool:
    """Evaluate a multipart ``when`` clause against blockstate props."""
    if not isinstance(when, dict):
        return False
    if "OR" in when:
        return any(_when_matches(c, props) for c in when["OR"])
    if "AND" in when:
        return all(_when_matches(c, props) for c in when["AND"])
    for key, value in when.items():
        prop_val = props.get(key)
        if isinstance(value, list):
            if prop_val not in value:
                return False
        elif prop_val != value:
            return False
    return True


# Shared with the fast tier (preview._DEFAULT_PROPS): default props for
# variant matching when the canonical blockstate omits them. Mirrors the
# trusted tier's convention (``props.get("facing", "north")`` etc.): a
# missing prop means the vanilla default blockstate, which is also what
# the validator accepts and what structure-loading fills in. Without
# these, bare names like ``minecraft:lantern`` match no variant and
# degrade to the fallback cube.
_DEFAULT_PROPS = _fast._DEFAULT_PROPS


def _model_applications(block_name: str, props: dict, root: Path):
    """List of (model_ref, x, y, uvlock) for a blockstate.

    Variants: most-specific match (ties → file order); a weighted list
    takes its FIRST entry (deterministic, same as the fast tier).
    Multipart: every matching case, in file order. Empty list when the
    blockstate is missing or nothing matches.
    """
    short = block_name.split(":", 1)[-1]
    bs = _read_json(root / "blockstates" / f"{short}.json")
    if not bs:
        return []
    # Fill missing props from defaults so partial canonical blockstates
    # (e.g. stairs without ``shape``) still match a variant.
    full_props = dict(_DEFAULT_PROPS)
    full_props.update(props)
    apps = []
    variants = bs.get("variants")
    if variants:
        var = _fast._match_variant(variants, full_props)
        if var and var.get("model"):
            apps.append((var["model"], int(var.get("x", 0)),
                         int(var.get("y", 0)), bool(var.get("uvlock", False))))
    elif bs.get("multipart"):
        for case in bs["multipart"]:
            when = case.get("when")
            if when is not None and not _when_matches(when, full_props):
                continue
            apply = case.get("apply")
            if isinstance(apply, list):
                apply = apply[0] if apply else None
            if isinstance(apply, dict) and apply.get("model"):
                apps.append((apply["model"], int(apply.get("x", 0)),
                             int(apply.get("y", 0)),
                             bool(apply.get("uvlock", False))))
    return apps


# ---------------------------------------------------------------------------
# quad construction
# ---------------------------------------------------------------------------

# A resolved quad: (points, normal, texture_image).
# points: 4 (x, y, z) in block-local 0–1 coords, in UV order
#   [(u0,v0), (u0,v1), (u1,v1), (u1,v0)].
# normal: world-space outward normal (axis-snapped).
# texture_image: cropped to the face UV rect, face-rotation applied,
#   shaded for the world normal. Ready to warp.

def _snap_normal(v):
    """Snap a near-axis normal to its dominant axis (for UV lookup)."""
    ax = max(range(3), key=lambda i: abs(v[i]))
    out = [0.0, 0.0, 0.0]
    out[ax] = 1.0 if v[ax] >= 0 else -1.0
    return tuple(out)


def _normal_name(n) -> str:
    return {
        (0.0, 1.0, 0.0): "up", (0.0, -1.0, 0.0): "down",
        (0.0, 0.0, -1.0): "north", (0.0, 0.0, 1.0): "south",
        (-1.0, 0.0, 0.0): "west", (1.0, 0.0, 0.0): "east",
    }[n]


def _face_base_corners(face: str, f, t):
    """4 corners of an element face (0–1 coords), arbitrary but fixed order."""
    x0, y0, z0 = f
    x1, y1, z1 = t
    return {
        "up": [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        "down": [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        "north": [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
        "south": [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        "west": [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],
        "east": [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],
    }[face]


def _order_corners_uv(corners, normal_name: str):
    """Order 4 corners as [(u0,v0), (u0,v1), (u1,v1), (u1,v0)]."""
    u_axis, u_min_is_u0, v_axis, v_min_is_v0 = _UV_AXES[normal_name]

    def key(c):
        u = c[u_axis]
        v = c[v_axis]
        ku = u if u_min_is_u0 else -u
        kv = v if v_min_is_v0 else -v
        return (ku, kv)

    # (ku,kv): (min,min)->(u0,v0); (min,max)->(u0,v1);
    #          (max,max)->(u1,v1); (max,min)->(u1,v0).
    s = sorted(corners, key=key)
    # s[0]=(min,min), s[3]=(max,max); the middles need disambiguation.
    p00 = s[0]
    p11 = s[3]
    mid = [c for c in s[1:3]]
    # (min,max) has min ku and max kv.
    def k(c):
        u = c[u_axis]
        v = c[v_axis]
        return (u if u_min_is_u0 else -u, v if v_min_is_v0 else -v)
    mids = sorted(mid, key=lambda c: k(c))
    # mids[0] vs mids[1]: one is (min,max), other (max,min).
    # Disambiguate by kv: max kv → (u0,v1), min kv → (u1,v0).
    p01 = max(mids, key=lambda c: k(c)[1])  # (u0,v1)
    p10 = min(mids, key=lambda c: k(c)[1])  # (u1,v0)
    return [p00, p01, p11, p10]


def _shade_image(img: Image.Image, factor: float) -> Image.Image:
    if factor >= 1.0:
        return img
    return img.point(lambda v: min(255, int(v * factor)))


def _face_uv_rotation_crop(img: Image.Image, rotation: int) -> Image.Image:
    """Apply a face's UV ``rotation`` (clockwise viewed from outside)."""
    r = rotation % 360
    if r == 90:
        return img.transpose(Image.Transpose.ROTATE_270)
    if r == 180:
        return img.transpose(Image.Transpose.ROTATE_180)
    if r == 270:
        return img.transpose(Image.Transpose.ROTATE_90)
    return img


def _resolve_block_quads(block_name: str, props: dict, root: Path,
                         tex_cache: dict, fallback_color, fallback_blocks: set):
    """Resolve one blockstate to textured quads. None → caller falls back."""
    apps = _model_applications(block_name, props, root)
    if not apps:
        return None
    quads = []
    for model_ref, x_deg, y_deg, uvlock in apps:
        elements, images = _resolve_model_elements_and_textures(
            model_ref, root, tex_cache)
        if not elements:
            return None
        for el in elements:
            try:
                f = [c / 16.0 for c in el["from"]]
                t = [c / 16.0 for c in el["to"]]
            except (KeyError, TypeError):
                # Corrupt element: degrade the whole block to the
                # fallback cube rather than aborting the render.
                return None
            el_rot = el.get("rotation")
            for face_name, face in el.get("faces", {}).items():
                if face_name not in _FACE_NORMALS:
                    continue
                corners = _face_base_corners(face_name, f, t)

                def _xform(p):
                    q = p
                    if el_rot:
                        q = _apply_element_rotation(
                            q, el_rot.get("origin", [8, 8, 8]),
                            el_rot.get("axis", "y"),
                            el_rot.get("angle", 0))
                    return _apply_model_rotation(q, x_deg, y_deg)

                local_n = _FACE_NORMALS[face_name]
                if el_rot:
                    # Rotate the normal as a direction: offset from the
                    # rotation origin by the unit normal, rotate the point,
                    # subtract back. Exact only for origin (0.5,0.5,0.5);
                    # harmless here because _snap_normal re-snaps to an
                    # axis on vanilla assets.
                    n = _apply_element_rotation(
                        (0.5 + local_n[0], 0.5 + local_n[1], 0.5 + local_n[2]),
                        el_rot.get("origin", [8, 8, 8]),
                        el_rot.get("axis", "y"), el_rot.get("angle", 0))
                    local_n = (n[0] - 0.5, n[1] - 0.5, n[2] - 0.5)
                world_n = _snap_normal(
                    _apply_model_rotation_dir(local_n, x_deg, y_deg))
                # Texture for this face.
                tex_var = (face.get("texture") or "").lstrip("#")
                img = images.get(tex_var)
                uv = face.get("uv", [0, 0, 16, 16])
                u0, v0, u1, v1 = (min(uv[0], uv[2]), min(uv[1], uv[3]),
                                  max(uv[0], uv[2]), max(uv[1], uv[3]))
                if img is None:
                    # Per-face graceful degradation (flat color, like the
                    # fast tier) — the block still renders.
                    fallback_blocks.add(block_name)
                    img = Image.new("RGB", (16, 16), fallback_color)
                    u0, v0, u1, v1 = 0, 0, 16, 16
                tw, th = img.size
                # UVs are in 0–16 texture space; scale to pixels.
                sx, sy = tw / 16.0, th / 16.0
                crop = img.crop((int(round(u0 * sx)), int(round(v0 * sy)),
                                 int(round(u1 * sx)), int(round(v1 * sy))))
                if crop.size[0] < 1 or crop.size[1] < 1:
                    continue
                crop = _face_uv_rotation_crop(
                    crop, int(face.get("rotation", 0)))
                # UV corner assignment: painted-on for BOTH uvlock values.
                # Vanilla semantics (verified against the blockstate/model
                # JSONs): the texture is attached to the model in model
                # space and carried through the x/y rotations. A naive
                # "world-fixed" assignment (sorting rotated corners by
                # world axes) breaks texel density on rotated non-square
                # faces (e.g. a stair tread under y=90: 8 texels/block
                # horizontally, 32 vertically) and degenerates for side
                # faces turned 90° (sort axis constant across corners) —
                # vanilla cannot do that, so painted-on is the only
                # density-preserving behavior.
                ordered = [_xform(p) for p in
                           _order_corners_uv(corners, face_name)]
                if uvlock:
                    # uvlock keeps the texture from rotating with the
                    # model: for SIDE faces, ensure v0 is at the top so
                    # the texture stays upright (painted-on alone would
                    # leave x-rotated sides, e.g. top-half stairs,
                    # upside-down). y-rotations preserve up, so this only
                    # ever triggers for x-rotations.
                    _, wn_y, _ = world_n
                    if abs(wn_y) < 0.5 and ordered[0][1] < ordered[1][1]:
                        # v0 below v1: flip v -> [(u0,v1),(u0,v0),
                        # (u1,v0),(u1,v1)].
                        ordered = [ordered[1], ordered[0],
                                   ordered[3], ordered[2]]
                shade = _SHADES.get(world_n, 0.75)
                quads.append((ordered, world_n,
                              _shade_image(crop, shade)))
    return quads


def _fallback_cube_quads(fallback_color):
    """Labeled-cube fallback: 6 magenta quads (label added by the caller)."""
    img = Image.new("RGB", (16, 16), fallback_color)
    quads = []
    f, t = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    for face_name in _FACE_NAMES:
        corners = _face_base_corners(face_name, f, t)
        ordered = _order_corners_uv(corners, face_name)
        n = _FACE_NORMALS[face_name]
        quads.append((ordered, n, _shade_image(img, _SHADES[n])))
    return quads


def resolve_block_quads(canonical: str, assets_root: Path | None,
                        tex_cache: dict, fallback_blocks: set | None = None):
    """Public helper: (quads, is_fallback) for one canonical block string."""
    name, props = _fast._split_blockstate(canonical)
    fallback_color = _FALLBACK_MAGENTA
    if fallback_blocks is None:
        fallback_blocks = set()
    if assets_root is None:
        return _fallback_cube_quads(fallback_color), True
    quads = _resolve_block_quads(
        name, props, assets_root, tex_cache, _fast._fallback_color(name),
        fallback_blocks)
    if not quads:
        return _fallback_cube_quads(fallback_color), True
    return quads, False


# ---------------------------------------------------------------------------
# drawing
# ---------------------------------------------------------------------------

def _draw_textured_quad(canvas: Image.Image, pts_uv, tex: Image.Image):
    """Warp a texture across a quad. pts_uv: [(sx,sy,tx,ty)] ×4 in UV order.

    The UV order is [(u0,v0), (u0,v1), (u1,v1), (u1,v0)] which matches the
    texture crop's corners [(0,0), (0,h), (w,h), (w,0)]. The order is cyclic
    (orthographic projection preserves cyclicity), so the texture→screen
    map is affine: solve it from the 4 correspondences and derive the
    correct QUAD data (texels at the output-rect corners). A screen-space
    "top two / bottom two" reorder would twist diamonds (top faces in iso
    get their texture rotated 90°); the affine solve is exact for all
    convex quads.
    """
    # Skip degenerate quads (edge-on to the camera, e.g. a zero-thickness
    # bar seen side-on): the affine fit is ill-conditioned and the warp
    # would smear black across the bounding box. A real rasterizer draws
    # nothing for zero-area triangles.
    _sx = [p[0] for p in pts_uv]
    _sy = [p[1] for p in pts_uv]
    _area2 = abs(sum(_sx[i] * _sy[(i + 1) % 4] - _sx[(i + 1) % 4] * _sy[i]
                     for i in range(4)))
    if _area2 < 2.0:  # < 1 px² screen-space area
        return
    # Affine texture->screen: screen = M @ tex + t. Solve from the 4
    # (cyclic) correspondences, then invert for screen->texture.
    src = np.array([(tx, ty) for _, _, tx, ty in pts_uv], dtype=float)
    dst = np.array([(sx, sy) for sx, sy, _, _ in pts_uv], dtype=float)
    A = np.column_stack([src, np.ones(4)])
    try:
        (m11, m12, t1), *_ = np.linalg.lstsq(A, dst[:, 0], rcond=None)
        (m21, m22, t2), *_ = np.linalg.lstsq(A, dst[:, 1], rcond=None)
        Minv = np.linalg.inv(np.array([[m11, m12], [m21, m22]]))
    except np.linalg.LinAlgError:
        return
    t = np.array([t1, t2])
    xs = [p[0] for p in pts_uv]
    ys = [p[1] for p in pts_uv]
    x0, x1 = math.floor(min(xs)), math.ceil(max(xs))
    y0, y1 = math.floor(min(ys)), math.ceil(max(ys))
    bw, bh = x1 - x0, y1 - y0
    if bw < 1 or bh < 1:
        return
    # AFFINE (not QUAD): the texture→screen map is affine by construction,
    # and PIL's QUAD (perspective) solver goes numerically unstable on
    # thin/axis-aligned quads — it smeared a black bowtie across the
    # lantern cross-bars. We do the affine warp directly with numpy
    # (PIL's AFFINE+NEAREST has the same bug on tiny textures):
    # tex = Minv @ (screen - t), screen = (ox + x0, oy + y0).
    a, b = float(Minv[0, 0]), float(Minv[0, 1])
    c = float(Minv[0, 0] * (x0 - t1) + Minv[0, 1] * (y0 - t2))
    d, e = float(Minv[1, 0]), float(Minv[1, 1])
    f = float(Minv[1, 0] * (x0 - t1) + Minv[1, 1] * (y0 - t2))
    tex_arr = np.array(tex)
    th_arr, tw_arr = tex_arr.shape[0], tex_arr.shape[1]
    _oy, _ox = np.mgrid[0:bh, 0:bw]
    _tx = np.clip((a * _ox + b * _oy + c).astype(int), 0, tw_arr - 1)
    _ty = np.clip((d * _ox + e * _oy + f).astype(int), 0, th_arr - 1)
    warped = Image.fromarray(tex_arr[_ty, _tx].astype(np.uint8), "RGB")
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon(
        [(sx - x0, sy - y0) for sx, sy, _, _ in pts_uv], fill=255)
    canvas.paste(warped, (x0, y0), mask)


def _soft_shadow_layer(W: int, H: int, proj_foot) -> Image.Image:
    """Blurred contact ellipse under the structure's projected footprint."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    xs = [p[0] for p in proj_foot]
    ys = [p[1] for p in proj_foot]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    rx = (max(xs) - min(xs)) * 0.52
    ry = (max(ys) - min(ys)) * 0.42 + rx * 0.12
    # Slight offset away from the light (light from upper-left).
    cx += rx * 0.08
    cy += ry * 0.18
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=(40, 35, 30, 95))
    # Blur proportional to output scale; the layer is at render scale.
    blur_r = max(8, int(0.035 * max(W, H)))
    layer = layer.filter(ImageFilter.GaussianBlur(blur_r))
    return layer


def _draw_title(img: Image.Image, title: str) -> None:
    """Pixel-style title, top-center, like the Shadow Court reference."""
    base_font = ImageFont.load_default()
    # Render small, then scale up for a chunky pixel look.
    tmp = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    lb = d.textbbox((0, 0), title, font=base_font)
    tw, th = lb[2] - lb[0] + 4, lb[3] - lb[1] + 4
    tmp = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((2, 2), title, font=base_font,
           fill=_TITLE_COLOR + (255,))
    scale = max(2, img.size[0] // 260)
    big = tmp.resize((tw * scale, th * scale), Image.NEAREST)
    img.paste(big, ((img.size[0] - big.size[0]) // 2,
                    int(img.size[1] * 0.045)), big)


def _draw_debug_badge(img: Image.Image) -> None:
    d = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default()
    text = "FAITHFUL · DIRECTIONS TRUSTED"
    lb = d.textbbox((0, 0), text, font=font)
    tw, th = lb[2] - lb[0], lb[3] - lb[1]
    pad = 5
    x, y = 10, 10
    d.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad],
                fill=(20, 90, 40, 200))
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def _render_view(arr, palette, crop, view, quad_cache, tex_cache,
                 assets_root, fallback_blocks, presentation, title):
    d, r, u = _fast._camera(view)
    (x0, x1), (y0, y1), (z0, z1) = crop
    ss = SUPERSAMPLE if presentation else 1

    corners = np.array([
        [x, y, z]
        for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)
    ], dtype=float)
    proj = _fast._project(corners, r, u)
    minx, miny = proj.min(axis=0)
    maxx, maxy = proj.max(axis=0)
    margin = PRESENTATION_MARGIN if presentation else _fast.MARGIN
    mx, my = margin / 2 * (maxx - minx), margin / 2 * (maxy - miny)
    minx -= mx
    maxx += mx
    miny -= my
    maxy += my
    # Headroom for the title in presentation mode.
    title_pad = 0.0
    if presentation and title:
        title_pad = (maxy - miny) * 0.16
        miny -= title_pad
    w2d, h2d = max(maxx - minx, 1e-9), max(maxy - miny, 1e-9)
    longest = PRESENTATION_LONGEST_PX if presentation else _fast.LONGEST_SIDE_PX
    scale = longest / max(w2d, h2d) * ss
    W, H = int(round(w2d * scale)), int(round(h2d * scale))

    def to_px(sx, sy):
        return (int(round((sx - minx) * scale)),
                int(round((maxy - sy) * scale)))

    bg = _BG_PRESENTATION if presentation else _BG_DEBUG
    canvas = Image.new("RGB", (W, H), bg)

    if presentation:
        # Soft contact shadow under the projected footprint.
        foot = np.array([
            [x, y0, z] for x in (x0, x1) for z in (z0, z1)
        ], dtype=float)
        proj_foot = [to_px(sx, sy)
                     for sx, sy in _fast._project(foot, r, u)]
        shadow = _soft_shadow_layer(W, H, proj_foot)
        canvas = Image.alpha_composite(
            canvas.convert("RGBA"), shadow).convert("RGB")

    # Collect quads: (depth, x, y, z, seq, pts3d, normal, tex).
    quads = []
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
        cached = quad_cache.get(idx)
        if cached is None:
            cached = resolve_block_quads(block, assets_root, tex_cache,
                                         fallback_blocks)
            quad_cache[idx] = cached
        (block_quads, _is_fallback) = cached
        x, y, z = lx + x0, ly + y0, lz + z0
        for pts, normal, tex in block_quads:
            if sum(n * dd for n, dd in zip(normal, d)) >= -1e-9:
                continue  # back-face culling
            wpts = [(px + x, py + y, pz + z) for px, py, pz in pts]
            depth = sum(p[i] * d[i] for p in wpts for i in range(3)) / 4.0
            quads.append((depth, x, y, z, seq, wpts, tex, _is_fallback, block))
            seq += 1

    quads.sort(key=lambda t: (-t[0], t[1], t[2], t[3], t[4]))
    # Screen-space centroids of fallback blocks, for debug-mode labels.
    fallback_labels: dict[str, list] = {}
    for _, _, _, _, _, wpts, tex, is_fb, block in quads:
        proj_pts = _fast._project(np.array(wpts), r, u)
        tw, th = tex.size
        # UV order [(u0,v0), (u0,v1), (u1,v1), (u1,v0)] ↔ texture
        # corners [(0,0), (0,h), (w,h), (w,0)].
        pairs = [(px, py, tx, ty) for (px, py), (tx, ty) in zip(
            [to_px(sx, sy) for sx, sy in proj_pts],
            [(0, 0), (0, th), (tw, th), (tw, 0)])]
        _draw_textured_quad(canvas, pairs, tex)
        if is_fb and not presentation:
            sx = sum(p[0] for p in pairs) / 4
            sy = sum(p[1] for p in pairs) / 4
            acc = fallback_labels.setdefault(block, [0.0, 0.0, 0])
            acc[0] += sx
            acc[1] += sy
            acc[2] += 1

    if presentation:
        if ss > 1:
            canvas = canvas.resize(
                (W // ss, H // ss), Image.LANCZOS)
        if title:
            _draw_title(canvas, title)
    else:
        _fast._overlay_label_and_compass(canvas, view, r, u)
        _draw_debug_badge(canvas)
        if fallback_labels:
            draw = ImageDraw.Draw(canvas)
            for block, (sx, sy, n) in fallback_labels.items():
                short = block.split(":", 1)[-1].split("[", 1)[0]
                draw.text((sx / n, sy / n), short, fill=(255, 255, 255))
    return canvas


def render(grid, out_dir, views: list[View], assets_dir,
           presentation: bool = True, title: str | None = None):
    """Render each view with the faithful tier. Returns ordered paths.

    ``presentation=True`` (default) produces the Shadow Court look
    (light background, soft shadow, title, no debug chrome);
    ``presentation=False`` is the debug view. Filenames encode the
    camera (``view.label + ".png"``). ``info`` carries
    ``untrusted_blocks`` (``{block_name: palette_count}`` for
    missing-model fallbacks — PLAN §3 per-type warnings),
    ``fallback_blocks`` (blocks with per-face texture fallbacks),
    ``assets_missing``, ``presentation`` and ``views``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    arr, palette, _provenance = grid.to_dense()
    arr = np.asarray(arr, dtype=np.int32)
    crop = _fast._crop_bounds(arr, palette)
    assets_root = _fast._resolve_assets_root(assets_dir)

    quad_cache: dict = {}
    tex_cache: dict = {}
    untrusted: dict[str, int] = {}
    fallback_blocks: set[str] = set()
    paths: list[Path] = []

    # Pre-scan palette for per-type warnings (once per build, not per view).
    # Uses the full resolve path so a missing MODEL json (blockstate ok,
    # model gone) is also caught — _model_applications alone would miss it.
    if crop is not None and assets_root is not None:
        for idx, block in enumerate(palette):
            if block in ("minecraft:air",):
                continue
            _quads, is_fallback = resolve_block_quads(
                block, assets_root, tex_cache, set())
            if is_fallback:
                name = _fast._split_blockstate(block)[0]
                untrusted[name] = untrusted.get(name, 0) + int((arr == idx).sum())

    for view in views:
        if crop is None:
            img = Image.new("RGB", (512, 512),
                            _BG_PRESENTATION if presentation else _BG_DEBUG)
            if presentation:
                if title:
                    _draw_title(img, title)
            else:
                d, r, u = _fast._camera(view)
                _fast._overlay_label_and_compass(img, view, r, u)
                _draw_debug_badge(img)
        else:
            img = _render_view(arr, palette, crop, view, quad_cache,
                               tex_cache, assets_root, fallback_blocks,
                               presentation, title)
        path = out / f"{view.label}.png"
        img.save(path)
        paths.append(path)

    info = {
        "assets_missing": assets_root is None,
        "assets_root": str(assets_root) if assets_root else None,
        "fallback_blocks": sorted(fallback_blocks),
        "untrusted_blocks": dict(sorted(untrusted.items())),
        "presentation": presentation,
        "views": len(views),
    }
    return _fast.RenderResult(paths, info)


RenderResult = _fast.RenderResult

__all__ = ["RenderResult", "render", "resolve_block_quads"]
