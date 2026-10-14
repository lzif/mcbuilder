"""Asset pipeline: fetch version-pinned registry + vanilla client assets.

``fetch(version, cache_dir)`` downloads into ``<cache_dir>/<version>/``:

- ``minecraft-data.json`` — block registry, normalized from
  PrismarineJS/minecraft-data ``blocks.json``.
- ``client/`` — vanilla textures, block models and blockstates extracted
  from *inside* the client JAR (served by Mojang Piston).

Nothing Mojang-owned is ever vendored in the repo — everything is
downloaded at user time. All downloads are idempotent: files that already
exist are skipped.

Version naming: both Piston and minecraft-data use the plain release id
(e.g. ``"26.2"`` — verified 2026-10-08 against the live Piston manifest and
minecraft-data's ``dataPaths.json``). If minecraft-data does not have the
requested version yet (its ``data/pc/<version>/blocks.json`` 404s),
``dataPaths.json`` is consulted for the closest older layout; if none
exists, an ``AssetError`` explains the situation.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from mcbuilder.errors import AssetError
from mcbuilder.registry import normalize_block_data

__all__ = ["fetch"]

MC_DATA_RAW = "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master"
PISTON_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

# Egress proxy for the authoring sandbox (no auth). It is only used when
# the hostname actually resolves here — on a normal workstation or VPS
# (where ``hatch-egress-proxy`` does not exist) no proxy env is set and
# standard direct connections work out of the box. A user-configured
# HTTPS_PROXY/HTTP_PROXY always wins (setdefault never clobbers it).
_PROXY = "http://hatch-egress-proxy:3130"
_PROXY_HOST, _PROXY_PORT = "hatch-egress-proxy", 3130

# Only these subtrees are extracted from the client JAR.
_CLIENT_PREFIXES = (
    "assets/minecraft/textures/block/",
    "assets/minecraft/models/block/",
    "assets/minecraft/blockstates/",
    "assets/minecraft/textures/entity/",
)
def _client_cache_complete(client_dir: Path) -> bool:
    """True iff every extracted-asset subtree is present and non-empty.

    The early-return guard used to check only ``blockstates/`` — caches
    created before a prefix was added to ``_CLIENT_PREFIXES`` (e.g.
    ``textures/entity/``) then silently lacked the new assets forever.
    Every prefix is checked now, so a stale cache re-fetches.
    """
    for prefix in _CLIENT_PREFIXES:
        d = client_dir / prefix
        if not (d.is_dir() and any(d.iterdir())):
            return False
    return True


def _maybe_configure_proxy() -> None:
    """Default to the sandbox egress proxy, but only where it exists.

    On machines where ``hatch-egress-proxy`` does not resolve (any normal
    workstation/VPS), the proxy env vars are left untouched so direct
    connections work. Never overrides an explicitly configured proxy.
    The DNS probe is best-effort: any failure means "no sandbox proxy".
    """
    if "HTTPS_PROXY" in os.environ or "HTTP_PROXY" in os.environ:
        return
    try:
        socket.getaddrinfo(_PROXY_HOST, _PROXY_PORT)
    except OSError:
        return
    os.environ.setdefault("HTTPS_PROXY", _PROXY)
    os.environ.setdefault("HTTP_PROXY", _PROXY)


def _http_get(url: str, timeout: int = 120) -> tuple[int, bytes]:
    """Single choke point for all HTTP in this module.

    Returns ``(status_code, body)``. Raises ``AssetError`` on connection
    failures. Tests monkeypatch this function — no real network is needed.
    """
    _maybe_configure_proxy()
    req = urllib.request.Request(url, headers={"User-Agent": "mcbuilder/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssetError(f"network request failed for {url}: {exc}") from exc


def _version_key(version: str) -> tuple[tuple[int, ...], int]:
    """Sortable key for MC version ids like ``"26.2"`` or ``"1.21.11"``.

    Snapshots/pre-releases sort below their release
    (``26.4-snapshot-3 < 26.4``).
    """
    base, _, suffix = version.partition("-")
    try:
        nums = tuple(int(part) for part in base.split("."))
    except ValueError:
        raise AssetError(f"cannot parse MC version {version!r}")
    if not nums:
        raise AssetError(f"cannot parse MC version {version!r}")
    return (nums, 0 if suffix else 1)


def _closest_pc_layout(version: str, data_paths: dict) -> str | None:
    """Newest minecraft-data ``blocks`` layout not newer than ``version``.

    Returns the layout path (e.g. ``"pc/26.1"``) or ``None`` when no
    minecraft-data layout covers the requested version.
    """
    pc = data_paths.get("pc", {})
    want = _version_key(version)
    best_key: str | None = None
    for key in pc:
        try:
            key_v = _version_key(key)
        except AssetError:
            continue
        if key_v <= want and (best_key is None or _version_key(best_key) < key_v):
            best_key = key
    if best_key is None:
        return None
    return pc[best_key]["blocks"]


def _fallback_layout(version: str) -> str:
    """Find the closest minecraft-data layout for a version it lacks."""
    status, body = _http_get(f"{MC_DATA_RAW}/data/dataPaths.json")
    if status != 200:
        raise AssetError(
            f"minecraft-data has no data/pc/{version}/blocks.json (HTTP 404) and "
            f"dataPaths.json could not be fetched (HTTP {status}); "
            "check the version string or your network connection."
        )
    try:
        data_paths = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssetError(f"could not parse minecraft-data dataPaths.json: {exc}")
    layout = _closest_pc_layout(version, data_paths)
    if layout is None:
        newest = None
        for key in data_paths.get("pc", {}):
            try:
                if newest is None or _version_key(newest) < _version_key(key):
                    newest = key
            except AssetError:
                continue
        raise AssetError(
            f"version {version!r} is not in PrismarineJS/minecraft-data yet "
            f"(newest pc layout available: {newest}); minecraft-data lags new "
            "releases — either wait for it to update or fetch with an older "
            "`--version` and accept the older registry."
        )
    return layout


def _fetch_registry(version: str, dest: Path, *, force: bool = False) -> None:
    target = dest / "minecraft-data.json"
    if target.is_file() and not force:
        return  # idempotent
    layout = f"pc/{version}"
    status, body = _http_get(f"{MC_DATA_RAW}/data/{layout}/blocks.json")
    if status == 404:
        # Version too new for minecraft-data — use the closest older layout.
        layout = _fallback_layout(version)
        status, body = _http_get(f"{MC_DATA_RAW}/data/{layout}/blocks.json")
    if status != 200:
        raise AssetError(
            f"could not download the block registry for {version!r} "
            f"(HTTP {status}); check the version string or your network connection."
        )
    try:
        raw = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssetError(f"could not parse the registry payload for {version!r}: {exc}")
    try:
        blocks = normalize_block_data(raw)
    except (ValueError, KeyError, TypeError) as exc:
        raise AssetError(
            f"registry payload for {version!r} had an unexpected shape: {exc}"
        )
    payload = {"version": version, "layout": layout, "blocks": blocks}
    target.write_text(json.dumps(payload), encoding="utf-8")


def _safe_extract(zf: zipfile.ZipFile, members: list[str], dest: Path) -> None:
    resolved = dest.resolve()
    for name in members:
        target = (dest / name).resolve()
        if target != resolved and resolved not in target.parents:
            raise AssetError(f"refusing to extract suspicious zip entry {name!r}")
    zf.extractall(dest, members)


def _fetch_client(version: str, dest: Path, *, force: bool = False) -> None:
    client_dir = dest / "client"
    if not force and _client_cache_complete(client_dir):
        return  # idempotent

    status, body = _http_get(PISTON_MANIFEST)
    if status != 200:
        raise AssetError(
            f"could not reach the Mojang Piston version manifest (HTTP {status}); "
            "check your network connection."
        )
    try:
        manifest = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AssetError(f"could not parse the Piston version manifest: {exc}")
    entry = next(
        (v for v in manifest.get("versions", []) if v.get("id") == version), None
    )
    if entry is None:
        raise AssetError(
            f"version {version!r} not found in Mojang's version manifest — "
            "check the version string (Piston uses plain release ids like "
            "'26.2' or '1.21.4')."
        )

    status, body = _http_get(entry["url"])
    if status != 200:
        raise AssetError(
            f"could not fetch the Piston version metadata for {version!r} "
            f"(HTTP {status})."
        )
    try:
        client = json.loads(body)["downloads"]["client"]
        jar_url, sha1 = client["url"], client["sha1"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise AssetError(
            f"Piston metadata for {version!r} has no usable downloads.client "
            f"entry: {exc}"
        )

    status, jar_bytes = _http_get(jar_url)
    if status != 200:
        raise AssetError(
            f"could not download the client jar for {version!r} (HTTP {status})."
        )
    if hashlib.sha1(jar_bytes).hexdigest() != sha1.lower():
        raise AssetError(
            f"client jar for {version!r} failed sha1 verification — "
            "the download may be corrupt; delete the cache dir and retry."
        )
    try:
        with zipfile.ZipFile(io.BytesIO(jar_bytes)) as zf:
            members = [
                n
                for n in zf.namelist()
                if n.startswith(_CLIENT_PREFIXES) and not n.endswith("/")
            ]
            if not members:
                raise AssetError(
                    f"client jar for {version!r} contained none of the expected "
                    "asset paths (textures/block, models/block, blockstates)."
                )
            _safe_extract(zf, members, client_dir)
            # The jar root's version.json carries the authoritative
            # DataVersion ("world_version"); the .nbt exporter prefers it
            # over its fallback table. Tolerate jars without it.
            if "version.json" in zf.namelist():
                _safe_extract(zf, ["version.json"], dest)
    except zipfile.BadZipFile as exc:
        raise AssetError(
            f"downloaded client jar for {version!r} is not a valid zip: {exc}"
        )


def fetch(version: str, cache_dir: Path, *, force: bool = False) -> Path:
    """Download assets for ``version`` into ``<cache_dir>/<version>/``.

    Writes ``minecraft-data.json`` (normalized block registry),
    ``version.json`` (client jar metadata incl. the authoritative
    DataVersion), and ``client/`` (vanilla textures, block models,
    blockstates extracted from the client JAR). Skips anything already
    present unless ``force=True`` (re-downloads everything). Returns the
    version directory. Raises ``AssetError`` on failure.
    """
    dest = Path(cache_dir) / version
    dest.mkdir(parents=True, exist_ok=True)
    _fetch_registry(version, dest, force=force)
    _fetch_client(version, dest, force=force)
    return dest
