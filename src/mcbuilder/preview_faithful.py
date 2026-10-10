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

Stair rows (e.g. from ``roof_gable``/``stairs_run``) interlock with no
see-through gap between rows — each row's tall back faces uphill toward
the next row up, the same closed geometry as a hand-built vanilla roof.
(Before the #4 facing fix the rows faced downhill and left real
0.5-block notches; that geometry was a bug, not a quirk.)
"""

from __future__ import annotations

import json
import math
import sys
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

#: Per-AO-level brightness multipliers for levels (0, 1, 2, 3).
#: Vanilla-derived approximation (NOT byte-verified from decompiled
#: vanilla — a single tunable constant): the 0.4 floor is corroborated
#: by the thelinuxseal/nanocraft commit (2026-09-26) "fix ambient
#: occlusion treating air as solid"; the linear 0.2 steps are the
#: standard reconstruction of vanilla's per-level ramp. Multiplies with
#: _SHADES (shade stays baked into the cached texture palette-level;
#: AO multiplies per-pixel at draw time: texel × shade × ao).
_AO_BRIGHTNESS = (0.4, 0.6, 0.8, 1.0)

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
            img = im.convert("RGBA")
            # Keep RGBA only when the texture actually uses transparency
            # (glass, leaves, stained glass...); opaque textures stay RGB.
            if img.getchannel("A").getextrema() == (255, 255):
                img = img.convert("RGB")
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

    def _sprite(value):
        # 26.2+ texture metadata form: {"sprite": "...", ...}
        if isinstance(value, dict):
            return value.get("sprite", "")
        return value

    def resolve(value, depth: int = 0):
        value = _sprite(value)
        if not isinstance(value, str) or not value.startswith("#") or depth > 8:
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


# ---------------------------------------------------------------------------
# smooth lighting: occlusion classification + per-vertex AO sampling
# ---------------------------------------------------------------------------

#: Blocks that never occlude AO even though their models fill the cube:
#: translucent in vanilla, so they don't block skylight for neighbors.
_AO_NON_OCCLUDING = frozenset({
    "minecraft:ice",
    "minecraft:slime_block",
    "minecraft:honey_block",
})


def _block_occludes_ao(canonical: str, assets_root, tex_cache) -> bool:
    """True iff the block's rendered shape fills its cell for AO purposes.

    Mirrors ``resolve_block_quads``' dispatch order (fluid → entity →
    model → fallback) so the classification always matches what is
    actually rendered, whatever the merge order of the accuracy gaps.

    Computed once per ``render()`` call per palette entry, then expanded
    to a padded cell grid (out-of-bounds = air = non-occluding). Partial
    blocks (stairs, slabs, walls, ...) are non-occluding at cell level —
    they fail the full-cube test. Documented v0 simplification vs
    vanilla (which samples sub-cell shapes): partial blocks don't *cast*
    AO onto neighbors but still *receive* it.
    """
    name, props = _fast._split_blockstate(canonical)
    if name == "minecraft:air":
        return False
    if name in _FLUID_RGBA:
        # Water/lava: translucent cube. Chest: solid wooden-box stand-in.
        return name == "minecraft:chest"
    if assets_root is None:
        return True  # magenta fallback cube
    # Entity-approximation path (block-entities gap). Guarded by hasattr:
    # pre-gap4 the function doesn't exist and this step is skipped
    # entirely (banners/chests fall through to the model/fallback path,
    # matching the pre-gap4 render).
    _this_module = sys.modules[__name__]
    if hasattr(_this_module, "_try_entity_quads"):
        entity_quads = _this_module._try_entity_quads(
            name, props, assets_root, tex_cache)
        if entity_quads is not None:
            # Banner-kind: thin cloth + pole + crossbar; nothing fills
            # the cube. Chest family: near-full compound box.
            return not name.endswith("_banner")
        # None → fall through (entity texture missing → the render
        # degrades identically to the model/fallback path below).
    if name in _AO_NON_OCCLUDING:
        return False
    if name.endswith("leaves"):
        # Vanilla treats leaves as opaque cubes for AO, even though the
        # texture is transparent (explicit exception to the texture
        # heuristic below).
        return True
    apps = _model_applications(name, props, assets_root)
    if not apps:
        return True  # fallback magenta cube
    try:
        covered = np.zeros((16, 16, 16), dtype=bool)
        face_imgs = []
        for model_ref, _x, _y, _uvlock in apps:
            elements, images = _resolve_model_elements_and_textures(
                model_ref, assets_root, tex_cache)
            if not elements:
                return True
            for el in elements:
                f = [max(0, min(16, int(round(c)))) for c in el["from"]]
                t = [max(0, min(16, int(round(c)))) for c in el["to"]]
                covered[f[0]:t[0], f[1]:t[1], f[2]:t[2]] = True
                for face in el.get("faces", {}).values():
                    var = (face.get("texture") or "").lstrip("#")
                    face_imgs.append(images.get(var))
        if not covered.all():
            return False
        # Every face texture must be opaque: None (missing → the
        # renderer degrades that face to an OPAQUE flat color, so opaque
        # is the render-consistent classification) or non-RGBA
        # (_load_texture_image demotes fully-opaque RGBA to RGB, so RGBA
        # ⟺ genuinely transparent pixels). Glass / stained glass are
        # non-occluding automatically.
        return all(img is None or img.mode != "RGBA" for img in face_imgs)
    except (KeyError, TypeError, ValueError, IndexError):
        # Corrupt element: the render degrades the whole block to the
        # fallback cube → occluding, matching the render.
        return True


def _quad_ao_levels(v_locals, normal, cell, occ_padded):
    """AO levels (0–3) for the 4 vertices of one quad, vectorized.

    ``v_locals``: (4, 3) array of vertex positions minus the cell's
    array coords (in [0, 1]; fractional allowed for partial blocks).
    ``normal``: the face's axis-snapped world normal. ``cell``: (x, y, z)
    array coords. ``occ_padded``: padded bool occlusion grid (+1 shift).

    Sampling rule (vanilla): for each vertex, in the face-adjacent
    layer, sample the two side cells and the corner cell (neighbor
    offset per tangent axis: −1 at the low edge, +1 at the high edge,
    0 for an interior vertex — which samples the cell directly outside
    the vertex). level = 0 if (side1 and side2)
    else 3 − (side1 + side2 + corner).
    """
    vl = np.asarray(v_locals, dtype=float)
    n = tuple(normal)
    ax = 0 if n[0] else (1 if n[1] else 2)
    t1, t2 = [t for t in (0, 1, 2) if t != ax]
    vt1 = vl[:, t1]
    vt2 = vl[:, t2]
    ot1 = np.where(vt1 <= 1e-9, -1, np.where(vt1 >= 1 - 1e-9, 1, 0))
    ot2 = np.where(vt2 <= 1e-9, -1, np.where(vt2 >= 1 - 1e-9, 1, 0))
    # Padded index of the face-adjacent cell.
    base = np.array(cell, dtype=int) + np.array(n, dtype=int) + 1
    e1 = np.zeros(3, dtype=int)
    e1[t1] = 1
    e2 = np.zeros(3, dtype=int)
    e2[t2] = 1
    i1 = base[None, :] + ot1[:, None] * e1[None, :]
    i2 = base[None, :] + ot2[:, None] * e2[None, :]
    ic = i1 + (i2 - base[None, :])
    s1 = occ_padded[i1[:, 0], i1[:, 1], i1[:, 2]]
    s2 = occ_padded[i2[:, 0], i2[:, 1], i2[:, 2]]
    c = occ_padded[ic[:, 0], ic[:, 1], ic[:, 2]]
    both = s1 & s2
    return np.where(
        both, 0,
        3 - (s1.astype(np.int64) + s2.astype(np.int64)
             + c.astype(np.int64)))


def _vertex_ao_level(v_local, normal, cell, occ_padded) -> int:
    """AO level (0–3) for one quad vertex. Canonical per-vertex sampler.

    ``v_local``: vertex position minus the cell's array coords (in
    [0, 1]; fractional allowed for partial blocks). See
    ``_quad_ao_levels`` for the sampling rule.
    """
    return int(_quad_ao_levels([v_local], normal, cell, occ_padded)[0])


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
    if img.mode == "RGBA":
        # Shade RGB only — alpha is transparency, not brightness.
        r, g, b, a = img.split()
        shaded = [c.point(lambda v: min(255, int(v * factor))) for c in (r, g, b)]
        return Image.merge("RGBA", (*shaded, a))
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
                    has_real_texture = False
                else:
                    has_real_texture = True
                tw, th = img.size
                # UVs are in 0–16 texture space; scale to pixels.
                sx, sy = tw / 16.0, th / 16.0
                crop = img.crop((int(round(u0 * sx)), int(round(v0 * sy)),
                                 int(round(u1 * sx)), int(round(v1 * sy))))
                if crop.size[0] < 1 or crop.size[1] < 1:
                    continue
                crop = _face_uv_rotation_crop(
                    crop, int(face.get("rotation", 0)))
                # Biome tint (plains default): multiply the tint into the
                # per-face crop — never into tex_cache, whose source images
                # are shared across blocks/palette entries. Faces without
                # tintindex (or blocks with no table entry) stay untinted;
                # missing-texture flat colors are never tinted (debug
                # signal). Applied before directional shading, matching
                # vanilla's tint-before-lighting order.
                ti = face.get("tintindex", -1)
                if (has_real_texture and isinstance(ti, int) and ti >= 0
                        and (tint := _fast._TINT_TABLE.get(block_name))
                        is not None):
                    crop = _fast._tint_image(crop, tint)
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


_FLUID_RGBA = {
    # Fluids have no block model (special in-game renderer): render as
    # translucent blue/orange cubes instead of the magenta fallback.
    "minecraft:water": (63, 118, 228, 150),
    "minecraft:lava": (255, 110, 20, 210),
    # Chests are block entities (no JSON model): plain wooden box.
    "minecraft:chest": (181, 140, 82, 255),
}

#: Still-fluid surface height: exactly 8/9 ≈ 0.8888889 (measured from the
#: official Java client — a source block's fluid amount 8 renders at 8/9).
#: Applies to both water and lava: vanilla runs both through the same
#: fluid renderer operating on FluidState (fluid-agnostic).
_FLUID_SURFACE_HEIGHT = 8.0 / 9.0

def _fluid_cube_quads(rgba, top_height: float = 1.0):
    """Translucent fluid cube: 6 shaded RGBA quads (alpha preserved).

    ``top_height`` lowers only the up face's top corners (still fluids sit
    at 8/9). Side faces span the full 0..1: vanilla clips them
    per-neighbor, but the per-palette quad cache has no neighbor context —
    documented approximation.
    """
    r, g, b, a = rgba
    quads = []
    f = (0.0, 0.0, 0.0)
    for face_name in _FACE_NAMES:
        t = (1.0, top_height if face_name == "up" else 1.0, 1.0)
        corners = _face_base_corners(face_name, f, t)
        ordered = _order_corners_uv(corners, face_name)
        n = _FACE_NORMALS[face_name]
        factor = _SHADES[n]
        img = Image.new(
            "RGBA", (16, 16),
            (min(255, int(r * factor)), min(255, int(g * factor)),
             min(255, int(b * factor)), a),
        )
        quads.append((ordered, n, img))
    return quads


# ---------------------------------------------------------------------------
# block-entity approximations (faithful tier)
# ---------------------------------------------------------------------------
# Chests and banners are block entities: vanilla ships no JSON model with
# elements for them, so the renderer approximates them from their entity
# textures (textures/entity/chest/*.png,
# textures/entity/banner/banner_base.png). UV regions below were measured
# from the real 26.2 PNGs (2026-10-10):
# - chest normal.png 64×64: lid band y0-18, body band y19-42, latch opaque
#   bbox (0,0)-(6,5) (metallic gray, mean 153).
# - banner_base.png 64×64: cloth panels (0,0)-(22,41) front / (22,0)-(42,41)
#   back (near-white, mean 241/225 — tintable), pole strip (44,0)-(52,42)
#   = 4 sides × 2px, bar strip (0,42)-(44,46).
# NOTE on the chest "front" side: the vanilla chest texture's front regions
# (body/lid front + latch) belong on the latch side of the block. The
# canonical orientation here puts the latch on the NORTH face (facing
# north, 0°), so the texture-front regions are painted on the north face —
# i.e. the vanilla unrotated model frame's +Z, rotated into the facing-
# north canonical frame.

#: Block name → entity texture rel (for _load_texture_image). Waxed copper
#: chests share their unwaxed stage's texture.
_ENTITY_TEXTURES = {
    "minecraft:chest": "entity/chest/normal",
    "minecraft:trapped_chest": "entity/chest/trapped",
    "minecraft:ender_chest": "entity/chest/ender",
    "minecraft:copper_chest": "entity/chest/copper",
    "minecraft:exposed_copper_chest": "entity/chest/copper_exposed",
    "minecraft:weathered_copper_chest": "entity/chest/copper_weathered",
    "minecraft:oxidized_copper_chest": "entity/chest/copper_oxidized",
    "minecraft:waxed_copper_chest": "entity/chest/copper",
    "minecraft:waxed_exposed_copper_chest": "entity/chest/copper_exposed",
    "minecraft:waxed_weathered_copper_chest": "entity/chest/copper_weathered",
    "minecraft:waxed_oxidized_copper_chest": "entity/chest/copper_oxidized",
}

#: Vanilla dye palette (long-stable; the white cloth base multiplies
#: cleanly into every dye color).
_DYE_RGB = {
    "white": (249, 255, 254),
    "orange": (249, 128, 29),
    "magenta": (199, 78, 189),
    "light_blue": (58, 179, 218),
    "yellow": (254, 216, 61),
    "lime": (128, 199, 31),
    "pink": (243, 139, 170),
    "gray": (71, 79, 82),
    "light_gray": (157, 157, 151),
    "cyan": (22, 156, 156),
    "purple": (137, 50, 184),
    "blue": (60, 68, 170),
    "brown": (131, 84, 50),
    "green": (94, 124, 22),
    "red": (176, 46, 38),
    "black": (29, 29, 33),
}

#: Chest part UVs, measured from the real 26.2 chest PNGs. Canonical front
#: (latch side) is the NORTH face (see the module note above).
_CHEST_BODY_UVS = {
    "north": (14, 33, 28, 43),  # front (latch side)
    "south": (42, 33, 56, 43),  # back
    "east": (28, 33, 42, 43),   # left (+X)
    "west": (0, 33, 14, 43),    # right (−X)
    "up": (14, 19, 28, 33),
    "down": (28, 19, 42, 33),
}
_CHEST_LID_UVS = {
    "north": (14, 14, 28, 19),
    "south": (42, 14, 56, 19),
    "east": (28, 14, 42, 19),
    "west": (0, 14, 14, 19),
    "up": (14, 0, 28, 14),
    "down": (28, 0, 42, 14),
}
_CHEST_LATCH_UV = (0, 0, 6, 5)  # measured opaque bbox (all latch faces)

_FACING_Y_ROT = {"north": 0, "east": 90, "south": 180, "west": 270}
_WALL_BANNER_Y_ROT = {"south": 0, "west": 90, "north": 180, "east": 270}


def _rot_y_degrees(p, degrees):
    """Continuous _rot_y: Y rotation, clockwise viewed from above.

    Matches _rot_y exactly at 90° multiples (pinned by test); used for
    standing-banner ``rotation`` (22.5° steps).
    """
    theta = math.radians(degrees)
    c, s = math.cos(theta), math.sin(theta)
    x, y, z = p
    vx, vz = x - 0.5, z - 0.5
    return (0.5 + c * vx - s * vz, y, 0.5 + s * vx + c * vz)


def _rot_y_degrees_dir(v, degrees):
    """Direction-vector twin of _rot_y_degrees (no center offset)."""
    theta = math.radians(degrees)
    c, s = math.cos(theta), math.sin(theta)
    vx, vy, vz = v
    return (c * vx - s * vz, vy, s * vx + c * vz)


def _entity_box_quads(f, t, face_uvs, img):
    """One textured box from an entity PNG, in canonical orientation.

    f, t: block-local 0–1 box corners; face_uvs: face -> (x0,y0,x1,y1)
    pixel rect. Returns [(ordered_points, canonical_normal, crop)] —
    crops are UNSHADED here; the caller rotates points+normals to the
    final orientation and shades for the world normal (painted-on UVs,
    world-space shading — the same rule as the model path). Faces absent
    from face_uvs are skipped (e.g. the pole's bottom).
    """
    quads = []
    for face_name, (x0, y0, x1, y1) in face_uvs.items():
        if face_name not in _FACE_NORMALS:
            continue
        corners = _face_base_corners(face_name, f, t)
        ordered = _order_corners_uv(corners, face_name)
        crop = img.crop((x0, y0, x1, y1))
        if crop.size[0] < 1 or crop.size[1] < 1:
            continue
        quads.append((ordered, _FACE_NORMALS[face_name], crop))
    return quads


def _finalize_entity_quads(quads, degrees, continuous=False):
    """Rotate entity quads to their final orientation + world-space shade.

    90° steps use _rot_y/_rot_y_dir; arbitrary angles use
    _rot_y_degrees with _snap_normal'd normals (shade 0.75 fallback for
    non-axis normals — same as diagonal sign boards today).
    """
    out = []
    for pts, n, crop in quads:
        if continuous:
            pts2 = [_rot_y_degrees(p, degrees) for p in pts]
            n2 = _snap_normal(_rot_y_degrees_dir(n, degrees))
        else:
            pts2 = [_rot_y(p, degrees) for p in pts]
            n2 = _snap_normal(_rot_y_dir(n, degrees))
        out.append((pts2, n2, _shade_image(crop, _SHADES.get(n2, 0.75))))
    return out


def _fill_transparent_corners(img, corners):
    """Fill fully-transparent texels with their opaque neighbor's color.

    Vanilla entity textures have rounded corners (isolated transparent
    texels); our crops would otherwise carry 1-texel pinholes.
    """
    d = ImageDraw.Draw(img)
    for x, y in corners:
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < img.size[0] and 0 <= ny < img.size[1]:
                r, g, b, a = img.getpixel((nx, ny))
                if a == 255:
                    d.point((x, y), fill=(r, g, b, 255))
                    break


def _chest_quads(props, img):
    """Single-chest approximation: body + lid + latch boxes.

    Canonical latch on the north face; ``facing`` rotates clockwise
    viewed from above ({north:0, east:90, south:180, west:270}).
    """
    if img.size != (64, 64):
        return None
    # The latch unwrap has two fully-transparent corner texels ((0,0) and
    # (5,0) — rounded corners in the vanilla texture); fill them from
    # their opaque neighbors so no pinhole shows on the latch corners.
    img = img.copy()
    _fill_transparent_corners(img, [(0, 0), (5, 0)])
    parts = _entity_box_quads(
        (1 / 16, 0.0, 1 / 16), (15 / 16, 10 / 16, 15 / 16),
        _CHEST_BODY_UVS, img)
    parts += _entity_box_quads(
        (1 / 16, 10 / 16, 1 / 16), (15 / 16, 15 / 16, 15 / 16),
        _CHEST_LID_UVS, img)
    latch_uvs = {face: _CHEST_LATCH_UV for face in _FACE_NAMES}
    parts += _entity_box_quads(
        (7 / 16, 11 / 16, 0.0), (9 / 16, 15 / 16, 1 / 16),
        latch_uvs, img)
    degrees = _FACING_Y_ROT.get(props.get("facing", "north"), 0)
    return _finalize_entity_quads(parts, degrees)


def _tint_rgb(img, rgb):
    """Multiply RGB channels by rgb/255 (white base → dye color)."""
    r, g, b = rgb
    if img.mode == "RGBA":
        cr, cg, cb, ca = img.split()
        tinted = [ch.point(lambda v, k=k: v * k // 255)
                  for ch, k in ((cr, r), (cg, g), (cb, b))]
        return Image.merge("RGBA", (*tinted, ca))
    cr, cg, cb = img.split()
    return Image.merge("RGB", [ch.point(lambda v, k=k: v * k // 255)
                               for ch, k in ((cr, r), (cg, g), (cb, b))])


def _banner_quads(props, img, dye_rgb, wall):
    """Banner approximation: pole + crossbar + tinted hanging cloth.

    Standing banners face south canonically; ``rotation`` (0–15) spins
    them in 22.5° steps. Wall banners hang on the wall opposite their
    ``facing`` (verified against oak_wall_sign's y-rotations:
    {south:0, west:90, north:180, east:270}). No pattern layers — only the
    base dye color (stated limitation).
    """
    if img.size != (64, 64):
        return None
    # Tint the cloth panels in a working copy; pole/bar stay wood.
    panel = img.copy()
    panel.paste(_tint_rgb(img.crop((0, 0, 22, 41)), dye_rgb), (0, 0))
    panel.paste(_tint_rgb(img.crop((22, 0, 42, 41)), dye_rgb), (22, 0))
    # Rounded transparent corner texels in the vanilla panels ((0,0) and
    # (41,0)); fill from the tinted neighbors to avoid pinholes.
    _fill_transparent_corners(panel, [(0, 0), (41, 0)])
    quads = []
    if not wall:
        # Pole (2×14×2); bottom face skipped (sits on the ground).
        pole_uvs = {
            "north": (44, 2, 46, 42),
            "south": (46, 2, 48, 42),
            "east": (48, 2, 50, 42),
            "west": (50, 2, 52, 42),
            "up": (46, 0, 48, 2),  # (44,0)-(46,2) has transparent corners
        }
        quads += _entity_box_quads(
            (7 / 16, 0.0, 7 / 16), (9 / 16, 14 / 16, 9 / 16),
            pole_uvs, img)
    # Crossbar (20×2×2); wood crops from the bar strip (approximate).
    # The strip's end columns (x 0-1, 42-43) have transparent corners, so
    # the bar ends sample just inside them.
    bar_uvs = {
        "north": (12, 42, 32, 44),
        "south": (12, 42, 32, 44),
        "east": (2, 42, 4, 44),
        "west": (40, 42, 42, 44),
        "up": (12, 42, 32, 44),
        "down": (12, 42, 32, 44),
    }
    if wall:
        quads += _entity_box_quads(
            (-2 / 16, 12 / 16, 0.0), (18 / 16, 14 / 16, 2 / 16),
            bar_uvs, img)
        cloth_f = (-2 / 16, 2 / 16, 0.5 / 16)
        cloth_t = (18 / 16, 12 / 16, 1.5 / 16)
    else:
        quads += _entity_box_quads(
            (-2 / 16, 12 / 16, 7 / 16), (18 / 16, 14 / 16, 9 / 16),
            bar_uvs, img)
        cloth_f = (-2 / 16, 2 / 16, 7.5 / 16)
        cloth_t = (18 / 16, 12 / 16, 8.5 / 16)
    # Cloth (20×10×1); thin edges sample the tinted panel's edge columns.
    cloth_uvs = {
        "south": (0, 0, 22, 41),    # front
        "north": (22, 0, 42, 41),   # back
        "east": (20, 0, 22, 41),
        "west": (0, 0, 2, 41),
        "up": (0, 0, 22, 2),
        "down": (0, 39, 22, 41),
    }
    quads += _entity_box_quads(cloth_f, cloth_t, cloth_uvs, panel)
    if wall:
        degrees = _WALL_BANNER_Y_ROT.get(props.get("facing", "north"), 0)
        return _finalize_entity_quads(quads, degrees)
    try:
        rotation = int(props.get("rotation", "0"))
    except (TypeError, ValueError):
        rotation = 0
    return _finalize_entity_quads(quads, (rotation % 16) * 22.5,
                                  continuous=True)


def _try_entity_quads(name, props, root, tex_cache):
    """Textured block-entity approximations (chest / banner families).

    Returns a quad list, or None when the block isn't entity-approximated
    or its entity texture failed to load (missing file, wrong size). None
    means the caller falls through to the existing behavior: chest →
    wooden box, trapped/ender/copper chests and banners → magenta cube.
    """
    if name in _ENTITY_TEXTURES:
        img = _load_texture_image(root, _ENTITY_TEXTURES[name], tex_cache)
        if img is None:
            return None
        return _chest_quads(props, img)
    short = name.split(":", 1)[-1]
    if short.endswith("_wall_banner"):
        color = short[: -len("_wall_banner")]
        wall = True
    elif short.endswith("_banner"):
        color = short[: -len("_banner")]
        wall = False
    else:
        return None
    dye = _DYE_RGB.get(color)
    if dye is None:
        return None
    img = _load_texture_image(root, "entity/banner/banner_base", tex_cache)
    if img is None:
        return None
    return _banner_quads(props, img, dye, wall)


def resolve_block_quads(canonical: str, assets_root: Path | None,
                        tex_cache: dict, fallback_blocks: set | None = None):
    """Public helper: (quads, is_fallback) for one canonical block string."""
    name, props = _fast._split_blockstate(canonical)
    fallback_color = _FALLBACK_MAGENTA
    if fallback_blocks is None:
        fallback_blocks = set()
    if assets_root is not None:
        entity_quads = _try_entity_quads(name, props, assets_root, tex_cache)
        if entity_quads is not None:
            # Intentional approximation, not a missing model: no
            # fallback warning.
            return entity_quads, False
    if name in _FLUID_RGBA:
        # Intentionally styled (not a missing model): no fallback warning.
        # Only actual fluids get the lowered surface — the chest is a
        # wooden box, not a fluid, and stays at full height.
        top_h = (_FLUID_SURFACE_HEIGHT
                 if name in ("minecraft:water", "minecraft:lava") else 1.0)
        return _fluid_cube_quads(_FLUID_RGBA[name], top_height=top_h), False
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

def _draw_textured_quad(canvas: Image.Image, pts_uv, tex: Image.Image,
                       ao=None):
    """Warp a texture across a quad. pts_uv: [(sx,sy,tx,ty)] ×4 in UV order.

    The UV order is [(u0,v0), (u0,v1), (u1,v1), (u1,v0)] which matches the
    texture crop's corners [(0,0), (0,h), (w,h), (w,0)]. The order is cyclic
    (orthographic projection preserves cyclicity), so the texture→screen
    map is affine: solve it from the 4 correspondences and derive the
    correct QUAD data (texels at the output-rect corners). A screen-space
    "top two / bottom two" reorder would twist diamonds (top faces in iso
    get their texture rotated 90°); the affine solve is exact for all
    convex quads.

    ``ao``: optional 4 per-vertex brightness factors in ``pts_uv`` order
    (smooth lighting). ``None`` — or all factors exactly 1.0 — renders
    byte-identical to the pre-AO behavior (fast path: the brightness
    pass is skipped entirely). Otherwise a single affine function is
    fit to the 4 (sx, sy) → factor correspondences (exact: every quad is
    an affine image of a planar rect, so screen quads are parallelograms
    where affine ≡ bilinear), evaluated over the bbox, clipped to
    [0, 1], and multiplied into the warped RGB only (alpha is
    transparency, same reasoning as ``_shade_image``'s RGB-only
    shading). ``.astype(np.uint8)`` truncation matches ``_shade_image``'s
    ``int(v * factor)`` semantics. Vanilla's quad-diagonal flip is
    deliberately skipped (no triangle split exists here); revisit only
    if corner gradients look twisted.
    """
    if ao is not None and all(a == 1.0 for a in ao):
        ao = None
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
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).polygon(
        [(sx - x0, sy - y0) for sx, sy, _, _ in pts_uv], fill=255)
    warped = tex_arr[_ty, _tx]
    if ao is not None:
        # Smooth lighting: affine brightness fit from the 4 vertex
        # factors (screen coords relative to the bbox, matching _ox/_oy).
        bsx = np.array([p[0] - x0 for p in pts_uv], dtype=float)
        bsy = np.array([p[1] - y0 for p in pts_uv], dtype=float)
        B = np.column_stack([bsx, bsy, np.ones(4)])
        (ba, bb, bc), *_ = np.linalg.lstsq(
            B, np.asarray(ao, dtype=float), rcond=None)
        bright = np.clip(ba * _ox + bb * _oy + bc, 0.0, 1.0)
        if tex.mode == "RGBA":
            # RGB only — alpha is transparency, not brightness.
            rgb = (warped[..., :3].astype(np.float32)
                   * bright[..., None]).astype(np.uint8)
            warped = np.dstack([rgb, warped[..., 3]])
        else:
            warped = (warped.astype(np.float32)
                      * bright[..., None]).astype(np.uint8)
    warped = warped.astype(np.uint8)
    if tex.mode == "RGBA":
        # Translucent quad (fluids): combine the quad-shape mask with the
        # texture alpha so the paste blends with what's behind it.
        warped_rgba = warped
        poly = np.array(mask).astype(np.float32) / 255.0
        eff = (poly * warped_rgba[..., 3].astype(np.float32)
               / 255.0 * 255.0).astype(np.uint8)
        canvas.paste(Image.fromarray(warped_rgba[..., :3], "RGB"),
                     (x0, y0), Image.fromarray(eff, "L"))
    else:
        canvas.paste(Image.fromarray(warped, "RGB"), (x0, y0), mask)


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
                 assets_root, fallback_blocks, presentation, title,
                 occ_padded):
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

    # Collect quads: (depth, x, y, z, seq, wpts, normal, tex,
    # _is_fallback, block). The normal rides along for per-vertex AO
    # sampling (it is not recomputed or altered anywhere downstream).
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
            quads.append((depth, x, y, z, seq, wpts, normal, tex,
                          _is_fallback, block))
            seq += 1

    quads.sort(key=lambda t: (-t[0], t[1], t[2], t[3], t[4]))
    # Screen-space centroids of fallback blocks, for debug-mode labels.
    fallback_labels: dict[str, list] = {}
    for _, x, y, z, _, wpts, normal, tex, is_fb, block in quads:
        proj_pts = _fast._project(np.array(wpts), r, u)
        tw, th = tex.size
        # UV order [(u0,v0), (u0,v1), (u1,v1), (u1,v0)] ↔ texture
        # corners [(0,0), (0,h), (w,h), (w,0)].
        pairs = [(px, py, tx, ty) for (px, py), (tx, ty) in zip(
            [to_px(sx, sy) for sx, sy in proj_pts],
            [(0, 0), (0, th), (tw, th), (tw, 0)])]
        # Smooth lighting: per-vertex AO from the padded occlusion grid.
        # v_local = vertex minus the cell's array coords (the sampler's
        # [0, 1] space). All level-3 → fast path (ao=None, pixel-identical
        # to pre-AO); otherwise multiply _AO_BRIGHTNESS at draw time.
        v_locals = np.asarray(wpts, dtype=float) - (x, y, z)
        levels = _quad_ao_levels(v_locals, normal, (x, y, z), occ_padded)
        if bool((levels == 3).all()):
            ao = None
        else:
            ao = [_AO_BRIGHTNESS[int(lv)] for lv in levels]
        _draw_textured_quad(canvas, pairs, tex, ao)
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

    # Ambient-occlusion opacity grid (smooth lighting): classified once
    # per render() call per palette entry (reuses tex_cache), then
    # expanded to a padded cell grid — out-of-bounds reads as air
    # (non-occluding). One grid for all views.
    occ_padded = None
    if crop is not None:
        occ_idx = np.zeros(len(palette), dtype=bool)
        for _idx, _block in enumerate(palette):
            occ_idx[_idx] = _block_occludes_ao(
                _block, assets_root, tex_cache)
        occ_padded = np.zeros(
            tuple(n + 2 for n in arr.shape), dtype=bool)
        _valid = arr >= 0  # -1 = UNSET → non-occluding
        occ_padded[1:-1, 1:-1, 1:-1][_valid] = occ_idx[arr[_valid]]

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
                               presentation, title, occ_padded)
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
