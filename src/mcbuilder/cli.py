"""Command-line interface for mcbuilder.

Subcommands:
  check   validate a builder script (fast loop: no rendering, no artifact)
  run     validate + export + render previews into an auto-versioned run dir
  assets  fetch/cache Minecraft assets (minecraft-data + vanilla client assets)

The builder script must define module-level ``BUILD`` (a ``mcbuilder.Build``
instance). View precedence: CLI ``--views``/``--count`` > script
``views_config`` > ``default_views()``.

All user-facing failures are clean one-line messages on stderr
(``mcbuild: error: ...``); tracebacks are never shown.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np

from mcbuilder import assets as assets_mod
from mcbuilder import build as build_mod
from mcbuilder import config as config_mod
from mcbuilder import errors as errors_mod
from mcbuilder import export_nbt as export_nbt_mod
from mcbuilder import preview as preview_mod
from mcbuilder import registry as registry_mod
from mcbuilder import report as report_mod
from mcbuilder import views as views_mod

DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "mcbuilder"
MAX_VIEWS = 36


class CliError(Exception):
    """A user-facing failure: reported as a clean message, never a traceback."""


# ---------------------------------------------------------------------------
# script loading
# ---------------------------------------------------------------------------

def _script_module_name(path: Path) -> str:
    # Stable per path so re-checks don't accumulate stale modules; the entry
    # is overwritten on every load.
    import hashlib

    digest = hashlib.sha1(os.path.abspath(path).encode()).hexdigest()[:12]
    return f"_mcbuild_script_{digest}"


def _load_script(path: Path):
    """Import the builder script as a module; return (module, BUILD instance)."""
    if not path.exists():
        raise CliError(f"script not found: {path}")
    if not path.is_file():
        raise CliError(f"not a file: {path}")
    name = _script_module_name(path)
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise CliError(f"cannot load script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Let scripts import sibling helpers from their own directory.
    script_dir = str(path.parent.resolve())
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        spec.loader.exec_module(module)
    except CliError:
        raise
    except Exception as e:  # noqa: BLE001 - surfaced as a clean message below
        raise CliError(
            f"failed to import {path.name}: {type(e).__name__}: {e}"
        ) from None
    build_obj = getattr(module, "BUILD", None)
    if build_obj is None:
        raise CliError(
            f"{path.name} does not define BUILD "
            "(module-level mcbuilder.Build instance is required)"
        )
    if not isinstance(build_obj, build_mod.Build):
        raise CliError(
            f"{path.name}: BUILD must be a mcbuilder.Build instance, "
            f"got {type(build_obj).__name__}"
        )
    return module, build_obj


# ---------------------------------------------------------------------------
# determinism static check (plan §2: warn, don't error)
# ---------------------------------------------------------------------------

def _scan_determinism(source: str, filename: str) -> list[str]:
    """Warn on raw ``random`` / ``np.random`` imports.

    ``Build(seed=...)`` is the sole RNG source, exposed as ``build.rng()``;
    the CLI pins PYTHONHASHSEED. Same script + same seed => same grid.
    """
    warnings: list[str] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return warnings  # the import step will report this cleanly
    hint = "use BUILD.rng() (from Build(seed=...)) for deterministic randomness"
    numpy_aliases: set[str] = set()

    def warn(msg: str) -> None:
        if msg not in warnings:
            warnings.append(msg)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "random":
                    warn(f"{filename}: imports 'random' — {hint}")
                elif alias.name == "numpy":
                    numpy_aliases.add(alias.asname or "numpy")
                elif alias.name == "numpy.random":
                    warn(f"{filename}: imports 'numpy.random' — {hint}")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "random":
                warn(f"{filename}: imports from 'random' — {hint}")
            elif node.module in ("numpy.random",):
                warn(f"{filename}: imports from 'numpy.random' — {hint}")
            elif node.module == "numpy" and any(a.name == "random" for a in node.names):
                warn(f"{filename}: imports 'random' from 'numpy' — {hint}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "random"
            and isinstance(node.value, ast.Name)
            and node.value.id in numpy_aliases
        ):
            warn(f"{filename}: uses '{node.value.id}.random' — {hint}")
            break
    return warnings


# ---------------------------------------------------------------------------
# config / registry
# ---------------------------------------------------------------------------

def _resolve_config(script_path: Path, explicit: str | None):
    """Explicit --config wins; otherwise discover mcbuild.toml from the script dir.

    Falls back to default config (mc_version "1.21.4") when no file is found.
    """
    if explicit:
        cfg_path = Path(explicit)
        try:
            return config_mod.McbuildConfig.load(cfg_path)
        except FileNotFoundError:
            raise CliError(f"config not found: {cfg_path}") from None
        except ValueError as e:
            raise CliError(f"invalid config {cfg_path}: {e}") from None
    try:
        found = config_mod.McbuildConfig.find(script_path.parent)
    except ValueError as e:
        raise CliError(f"invalid mcbuild.toml: {e}") from None
    return found if found is not None else config_mod.McbuildConfig()


def _cache_root(cfg) -> Path:
    if getattr(cfg, "assets_dir", None):
        return Path(cfg.assets_dir)
    return DEFAULT_CACHE_ROOT


def _load_registry(cfg):
    # Registry.load joins <cache_dir>/<version>/ itself, so it takes the
    # unversioned cache root (unlike preview, which prefers the version dir).
    try:
        return registry_mod.Registry.load(cfg.mc_version, _cache_root(cfg))
    except registry_mod.RegistryError as e:
        raise CliError(str(e)) from None


# ---------------------------------------------------------------------------
# validation + provenance
# ---------------------------------------------------------------------------

def _join_provenance(errors: list, palette: list[str], provenance: dict) -> list:
    """Attach ``at: "file:line"`` to each error via the palette-index provenance map."""
    for err in errors:
        if not isinstance(err, dict) or "at" in err:
            continue
        idx = err.get("palette_index", err.get("index"))
        if idx is None and "block" in err:
            try:
                idx = palette.index(err["block"])
            except ValueError:
                idx = None
        loc = provenance.get(idx) if isinstance(idx, int) else None
        err["at"] = f"{loc[0]}:{loc[1]}" if loc else "unknown"
    return errors


def _load_and_validate(script_arg: str, config_arg: str | None) -> dict:
    """Shared pipeline for check/run: load script, static scan, validate palette."""
    script = Path(script_arg)
    _module, build_obj = _load_script(script)
    cfg = _resolve_config(script, config_arg)
    det_warnings = _scan_determinism(script.read_text(encoding="utf-8"), script.name)
    reg = _load_registry(cfg)
    allowlist = getattr(cfg, "allowlist", None) or ()
    arr, palette, provenance = build_obj.grid.to_dense()
    errors, warnings = reg.validate(palette, allowlist=allowlist)
    errors = _join_provenance(errors, palette, provenance)
    return {
        "script": script,
        "build": build_obj,
        "config": cfg,
        "grid": build_obj.grid,
        "dense": arr,
        "palette": palette,
        "errors": errors,
        "warnings": list(warnings)
        + [{"message": w} for w in det_warnings],
    }


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------

def _resolve_views(args, build_obj) -> list:
    """CLI --views/--count > script views_config > default_views(). Max 36."""
    try:
        if args.views:
            view_list = views_mod.parse_views(args.views)
        else:
            script_views = getattr(build_obj, "views_config", None)
            if script_views:
                if isinstance(script_views[0], str):
                    view_list = views_mod.parse_views(";".join(script_views))
                else:
                    view_list = list(script_views)
            else:
                view_list = views_mod.default_views()
        if args.count:
            view_list = views_mod.with_count(view_list, args.count)
    except views_mod.ViewError as e:
        raise CliError(f"invalid views: {e}") from None
    except ValueError as e:
        raise CliError(f"invalid views: {e}") from None
    if len(view_list) > MAX_VIEWS:
        raise CliError(f"too many views: {len(view_list)} (max {MAX_VIEWS})")
    if not view_list:
        raise CliError("no views configured")
    return view_list


# ---------------------------------------------------------------------------
# report helpers
# ---------------------------------------------------------------------------

def _block_counts(arr: np.ndarray, palette: list[str]) -> dict[str, int]:
    """Survival material/shopping list: post-crop, air excluded.

    The dense array is already cropped to the non-air bbox; never-placed
    cells inside it read as -1 (UNSET) and are skipped. Counting non-air
    cells over the array therefore equals the post-crop material list.
    """
    counts: dict[str, int] = {}
    uniq, nums = np.unique(arr, return_counts=True)
    for i, n in zip(uniq.tolist(), nums.tolist()):
        i = int(i)
        if i < 0:
            continue
        name = palette[i]
        if name == "minecraft:air":
            continue
        counts[name] = counts.get(name, 0) + int(n)
    return counts


def _dimensions(grid, arr: np.ndarray) -> list[int]:
    """Post-crop bbox dimensions [dx, dy, dz]."""
    try:
        bounds = grid.bounds()
    except Exception:  # noqa: BLE001 - fall back to the raw array shape
        bounds = None
    if bounds is None:
        return [int(d) for d in arr.shape]
    (x0, y0, z0), (x1, y1, z1) = bounds
    return [int(x1 - x0 + 1), int(y1 - y0 + 1), int(z1 - z0 + 1)]


def _fmt_issue(issue) -> str:
    if isinstance(issue, dict):
        msg = str(issue.get("message", issue))
        at = issue.get("at")
        sug = issue.get("suggestion", issue.get("did_you_mean"))
        if sug is None:
            sugs = issue.get("suggestions") or []
            sug = ", ".join(str(s) for s in sugs) if sugs else None
        if at:
            msg += f" (at {at})"
        if sug:
            msg += f" — did you mean '{sug}'?"
        return msg
    return str(issue)


# ---------------------------------------------------------------------------
# artifact export (.nbt serializer)
# ---------------------------------------------------------------------------

def _export_artifact(
    grid, run_dir: Path, stem: str, *, cfg, include_air: bool
) -> tuple[Path, int, list[str]]:
    """Write the vanilla structure-block ``.nbt`` deploy artifact.

    Returns ``(path, data_version, warnings)``. Raises :class:`CliError`
    (clean message, no traceback) when the version's DataVersion can't be
    resolved or the grid can't be exported.
    """
    try:
        data_version = export_nbt_mod.resolve_data_version(
            cfg.mc_version, cfg.resolve_assets_dir()
        )
    except export_nbt_mod.ExportError as e:
        raise CliError(str(e)) from None
    out = run_dir / f"{stem}.nbt"
    try:
        warnings = export_nbt_mod.write_structure_nbt(
            grid, out, data_version=data_version, include_air=include_air
        )
    except export_nbt_mod.ExportError as e:
        raise CliError(str(e)) from None
    return out, data_version, warnings


# ---------------------------------------------------------------------------
# run dirs
# ---------------------------------------------------------------------------

def _next_run_dir(out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    n = 1
    while (out / f"run-{n:03d}").exists():
        n += 1
    run_dir = out / f"run-{n:03d}"
    run_dir.mkdir()
    return run_dir


# ---------------------------------------------------------------------------
# subcommands
# ---------------------------------------------------------------------------

def cmd_check(args) -> int:
    ctx = _load_and_validate(args.script, args.config)
    n_blocks = int(ctx["grid"].count_non_air())
    n_types = len(ctx["palette"])
    n_err, n_warn = len(ctx["errors"]), len(ctx["warnings"])
    status = "OK" if n_err == 0 else "FAILED"
    print(
        f"{ctx['script'].name} — {status} "
        f"({n_blocks} blocks, {n_types} types, {n_err} errors, {n_warn} warnings)"
    )
    for e in ctx["errors"]:
        print(f"  error: {_fmt_issue(e)}")
    for w in ctx["warnings"]:
        print(f"  warning: {_fmt_issue(w)}")
    return 1 if n_err else 0


def cmd_run(args) -> int:
    ctx = _load_and_validate(args.script, args.config)
    build_obj = ctx["build"]
    grid, arr, palette = ctx["grid"], ctx["dense"], ctx["palette"]
    errors, warnings = ctx["errors"], ctx["warnings"]

    view_list = _resolve_views(args, build_obj)

    out = Path(args.out)
    run_dir = _next_run_dir(out)
    stem = ctx["script"].stem
    previews_dir = run_dir / "previews"

    preview_paths: list[Path] = []
    if not errors and args.preview:
        try:
            preview_paths = preview_mod.render(
                grid, previews_dir, view_list, ctx["config"].resolve_assets_dir()
            )
        except Exception as e:  # noqa: BLE001 - clean message, no traceback
            raise CliError(f"preview render failed: {type(e).__name__}: {e}") from None

    if not errors:
        artifact_path, data_version, export_warnings = _export_artifact(
            grid, run_dir, stem, cfg=ctx["config"], include_air=args.include_air
        )
        warnings.extend({"message": w} for w in export_warnings)
        try:
            rel = artifact_path.relative_to(run_dir)
        except ValueError:
            rel = Path(artifact_path.name)
        artifacts = [
            {
                "file": str(rel),
                "format": "nbt",
                "data_version": data_version,
            }
        ]
    else:
        artifacts = []

    views_array = []
    for view, p in zip(view_list, preview_paths):
        try:
            rel = p.relative_to(run_dir)
        except ValueError:
            rel = Path(p.name)
        # Fast tier: flat textures, directions not trustworthy.
        views_array.append(
            report_mod.view_entry(
                file=str(rel), view=view, directions_untrusted=True
            )
        )

    report = report_mod.build_report(
        errors=errors,
        warnings=warnings,
        block_counts=_block_counts(arr, palette),
        dimensions=_dimensions(grid, arr),
        views=views_array,
        run_dir=str(run_dir),
        artifacts=artifacts,
    )
    try:
        report_mod.write_report(report, run_dir / "report.json")
    except Exception as e:  # noqa: BLE001 - clean message, no traceback
        raise CliError(
            f"failed to write report.json: {type(e).__name__}: {e}"
        ) from None

    n_blocks = int(grid.count_non_air())
    dims = _dimensions(grid, arr)
    print(f"run dir: {run_dir}")
    print(
        f"  {n_blocks} blocks, {len(palette)} types, "
        f"dims {'x'.join(str(d) for d in dims)} — "
        f"{len(errors)} errors, {len(warnings)} warnings"
    )
    if preview_paths:
        print(f"  previews: {len(preview_paths)} in {previews_dir.name}/")
    if artifacts:
        a = artifacts[0]
        print(f"  artifact: {a['file']} ({a['format']}, DataVersion {a['data_version']})")
    for e in errors:
        print(f"  error: {_fmt_issue(e)}")
    for w in warnings:
        print(f"  warning: {_fmt_issue(w)}")
    return 1 if errors else 0


def cmd_assets_fetch(args) -> int:
    cache_dir = (
        Path(args.cache_dir).expanduser() if args.cache_dir else DEFAULT_CACHE_ROOT
    )
    try:
        result = assets_mod.fetch(args.version, cache_dir)
    except errors_mod.AssetError as e:
        raise CliError(f"assets fetch failed: {e}") from None
    print(result)
    return 0


# ---------------------------------------------------------------------------
# argparse + entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcbuild",
        description=(
            "mcbuilder CLI — validate, export and preview agent-built "
            "Minecraft structures."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<command>")

    c = sub.add_parser(
        "check",
        help="validate a builder script (fast loop: no rendering, no artifact)",
    )
    c.add_argument("script", help="builder script defining module-level BUILD")
    c.add_argument(
        "--config",
        default=None,
        help="path to mcbuild.toml (default: discover from the script's directory)",
    )
    c.set_defaults(func=cmd_check)

    r = sub.add_parser(
        "run",
        help="validate, export and render a builder script into a versioned run dir",
    )
    r.add_argument("script", help="builder script defining module-level BUILD")
    r.add_argument(
        "--out",
        default="dist/",
        help="output directory for versioned run dirs (default: dist/)",
    )
    r.add_argument(
        "--preview",
        action="store_true",
        help="render preview PNGs into <run>/previews/",
    )
    r.add_argument(
        "--views",
        default=None,
        help="semicolon-separated view shorthands, e.g. 'az045_el025;top' "
        "(overrides the script's views_config)",
    )
    r.add_argument(
        "--count",
        type=int,
        default=None,
        help="append an orbit of N views at el25 after the resolved views",
    )
    r.add_argument(
        "--config",
        default=None,
        help="path to mcbuild.toml (default: discover from the script's directory)",
    )
    r.add_argument(
        "--include-air",
        action="store_true",
        help="include air blocks in the deploy artifact",
    )
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("assets", help="manage cached Minecraft assets")
    asub = a.add_subparsers(dest="assets_cmd", required=True, metavar="<command>")
    f = asub.add_parser(
        "fetch",
        help="fetch minecraft-data + vanilla client assets for a version",
    )
    f.add_argument("--version", required=True, help="Minecraft version, e.g. 1.21.4")
    f.add_argument(
        "--cache-dir",
        default=None,
        help="cache directory (default: ~/.cache/mcbuilder)",
    )
    f.set_defaults(func=cmd_assets_fetch)
    return p


def main(argv=None) -> int:
    # Plan §2 determinism: pin the hash seed for the whole process before
    # anything else runs. Re-exec so the pin applies from interpreter start.
    if os.environ.get("PYTHONHASHSEED") is None:
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = "0"
        os.execvpe(sys.executable, [sys.executable, *sys.argv], env)
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CliError as e:
        print(f"mcbuild: error: {e}", file=sys.stderr)
        return 1
    except errors_mod.McbuilderError as e:
        print(f"mcbuild: error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("mcbuild: interrupted", file=sys.stderr)
        return 130
    except BrokenPipeError:
        return 1
    except Exception as e:  # noqa: BLE001 - never a traceback
        print(f"mcbuild: error: unexpected {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
