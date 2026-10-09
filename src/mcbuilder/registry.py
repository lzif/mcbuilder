"""Block registry validator.

Validates canonical block strings (``namespace:name[prop=value,...]{nbt}``, as
produced by ``mcbuilder.blocks.canonicalize``) against a version-pinned block
registry derived from PrismarineJS minecraft-data.

Unknown names produce errors with did-you-mean suggestions — the registry
never silently rewrites a name. Block-entity NBT is opaque: only brace
balance is syntax-checked, never schema-validated.
"""

from __future__ import annotations

import difflib
import json
import re
from pathlib import Path

from mcbuilder.errors import RegistryError

__all__ = ["Registry", "normalize_block_data"]

_AIR = "minecraft:air"

# name [ [props] ] [{nbt}] — props cannot contain ']', NBT runs to end of string.
_BLOCK_RE = re.compile(r"^([^[{]+)(?:\[([^\]]*)\])?(\{.*\})?$", re.DOTALL)


def normalize_block_data(raw: object) -> dict[str, dict]:
    """Normalize raw minecraft-data into the registry mapping.

    Accepts either the raw list format of PrismarineJS/minecraft-data
    ``blocks.json`` or an already-normalized ``{"blocks": {...}}`` mapping
    (as written by ``mcbuilder.assets.fetch``).

    Returns ``{namespaced_name: {"properties": {prop: [legal values]}}}``.
    """
    if isinstance(raw, list):
        blocks: dict[str, dict] = {}
        for entry in raw:
            name = "minecraft:" + entry["name"]
            props: dict[str, list[str]] = {}
            for state in entry.get("states", []):
                values = state.get("values")
                if values is None:
                    # minecraft-data omits "values" for bool states.
                    values = ["true", "false"] if state.get("type") == "bool" else []
                props[state["name"]] = [str(v) for v in values]
            blocks[name] = {"properties": props}
        return blocks
    if isinstance(raw, dict) and isinstance(raw.get("blocks"), dict):
        blocks = {}
        for name, info in raw["blocks"].items():
            props = (info or {}).get("properties", {}) or {}
            blocks[name] = {
                "properties": {p: [str(v) for v in vals] for p, vals in props.items()}
            }
        return blocks
    raise ValueError(
        "unrecognized registry data: expected a minecraft-data blocks.json list "
        'or a {"blocks": {...}} mapping'
    )


def _split_block(block: str) -> tuple[str, dict[str, str], str | None]:
    """Split a canonical block string into (name, properties, nbt)."""
    match = _BLOCK_RE.match(block.strip())
    if not match:
        raise ValueError(f"malformed block string: {block!r}")
    name = match.group(1).strip()
    if not name:
        raise ValueError(f"malformed block string (empty name): {block!r}")
    props: dict[str, str] = {}
    raw_props = match.group(2)
    if raw_props is not None:
        for part in raw_props.split(","):
            part = part.strip()
            if not part:
                continue
            if "=" not in part:
                raise ValueError(
                    f"malformed property {part!r} in {block!r} (want name=value)"
                )
            key, value = part.split("=", 1)
            props[key.strip()] = value.strip()
    return name, props, match.group(3)


def _nbt_balanced(nbt: str) -> bool:
    """True if braces/brackets/parens in the NBT string are balanced.

    Quoted strings (single or double, backslash escapes honored) are skipped,
    so braces inside string values do not count.
    """
    closers = {"}": "{", "]": "[", ")": "("}
    stack: list[str] = []
    i, n = 0, len(nbt)
    while i < n:
        ch = nbt[i]
        if ch in "\"'":
            i += 1
            while i < n and nbt[i] != ch:
                if nbt[i] == "\\":
                    i += 1
                i += 1
            i += 1  # skip the closing quote (or run off the end)
            continue
        if ch in "{[(":
            stack.append(ch)
        elif ch in closers:
            if not stack or stack.pop() != closers[ch]:
                return False
        i += 1
    return not stack


class Registry:
    """Version-pinned block registry used to validate builder palettes."""

    def __init__(self, blocks: dict[str, dict], version: str):
        self.version = version
        self.blocks: dict[str, dict[str, list[str]]] = {}
        for name, info in blocks.items():
            props = (info or {}).get("properties", {}) or {}
            self.blocks[name] = {
                p: [str(v) for v in vals] for p, vals in props.items()
            }

    @classmethod
    def load(cls, version: str, cache_dir: Path) -> "Registry":
        """Load the registry for ``version`` from the assets cache.

        Reads ``<cache_dir>/<version>/minecraft-data.json`` as written by
        ``mcbuilder.assets.fetch``.
        """
        path = Path(cache_dir) / version / "minecraft-data.json"
        if not path.is_file():
            raise RegistryError(
                f"block registry for version {version!r} not found at {path} — "
                f"run `mcbuild assets fetch --version {version}` first."
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RegistryError(f"could not parse registry file {path}: {exc}")
        try:
            blocks = normalize_block_data(raw)
        except ValueError as exc:
            raise RegistryError(f"registry file {path} has an unexpected shape: {exc}")
        return cls(blocks, version)

    def names(self) -> list[str]:
        """All known block names (namespaced), sorted."""
        return sorted(self.blocks)

    def _suggest(self, name: str, n: int = 3) -> list[str]:
        """Did-you-mean candidates for an unknown block name."""
        candidates = self.names()
        try:
            from mcbuilder.blocks import suggest
        except ImportError:
            suggest = None  # type: ignore[assignment]
        if suggest is not None:
            try:
                return list(suggest(name, candidates))[:n]
            except TypeError:
                # Older/alternate signature: suggest(name).
                return list(suggest(name))[:n]
        return difflib.get_close_matches(name, candidates, n=n, cutoff=0.6)

    @staticmethod
    def _allowlist_name(entry: str) -> str:
        try:
            name, _, _ = _split_block(entry)
        except ValueError:
            return entry.strip()
        return name

    def validate(
        self, palette: list[str], allowlist: list[str] = ()
    ) -> tuple[list[dict], list[dict]]:
        """Validate a palette of canonical block strings.

        Returns ``(errors, warnings)`` where each error is
        ``{"block": str, "message": str, "suggestions": [str]}`` and each
        warning is ``{"block": str, "message": str}``.

        Rules:
        - unknown name → error + did-you-mean (never silently rewritten);
        - illegal property name/value → error listing the legal values;
        - allowlisted custom (non-vanilla) name → pass with an
          "unvalidated, unvalidated, build at own risk" warning;
        - block-entity NBT is opaque: only brace balance is checked;
        - ``minecraft:air`` is always legal.
        """
        errors: list[dict] = []
        warnings: list[dict] = []
        allowed = {self._allowlist_name(a) for a in allowlist}

        for block in palette:
            try:
                name, props, nbt = _split_block(block)
            except ValueError as exc:
                errors.append(
                    {"block": block, "message": str(exc), "suggestions": []}
                )
                continue

            if name == _AIR:
                continue  # minecraft:air is always legal

            if nbt is not None and not _nbt_balanced(nbt):
                errors.append(
                    {
                        "block": block,
                        "message": f"unbalanced braces/brackets in block-entity NBT of {block!r}",
                        "suggestions": [],
                    }
                )
                continue

            info = self.blocks.get(name)
            if info is None:
                if name in allowed:
                    warnings.append(
                        {
                            "block": block,
                            "message": (
                                f"{name} is allowlisted: unvalidated, "
                                "build at own risk"
                            ),
                        }
                    )
                    continue
                if ":" in name and not name.startswith("minecraft:"):
                    errors.append(
                        {
                            "block": block,
                            "message": (
                                f"unknown block {name!r} (not in the {self.version} "
                                "registry); add it to `allowlist` in mcbuild.toml "
                                "if it is a modded/custom block"
                            ),
                            "suggestions": [],
                        }
                    )
                else:
                    errors.append(
                        {
                            "block": block,
                            "message": (
                                f"unknown block {name!r} "
                                f"(not in the {self.version} registry)"
                            ),
                            "suggestions": self._suggest(name),
                        }
                    )
                continue

            for prop, value in props.items():
                legal = info.get(prop)
                if legal is None:
                    errors.append(
                        {
                            "block": block,
                            "message": (
                                f"unknown property {prop!r} on {name}; "
                                f"legal properties: {sorted(info)}"
                            ),
                            "suggestions": difflib.get_close_matches(
                                prop, list(info), n=3, cutoff=0.6
                            ),
                        }
                    )
                    continue
                if value not in legal:
                    hint = ""
                    if value.lower() in [v.lower() for v in legal]:
                        hint = (
                            f" (did you mean {value.lower()!r}? "
                            "values are case-sensitive)"
                        )
                    errors.append(
                        {
                            "block": block,
                            "message": (
                                f"illegal value {value!r} for property {prop!r} "
                                f"on {name}{hint}; legal values: {legal}"
                            ),
                            "suggestions": [],
                        }
                    )

        return errors, warnings
