"""``mcbuild.toml`` project configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python 3.10 — tomllib is 3.11+
    import tomli as tomllib

__all__ = ["McbuildConfig"]

_DEFAULT_MAX_DIMENSIONS = (256, 256, 256)


@dataclass
class McbuildConfig:
    """Project configuration, loaded from ``mcbuild.toml``.

    Example::

        mc_version = "26.2"
        max_dimensions = [256, 256, 256]
        allowlist = ["lostqol:waystone"]  # pass validation, warn at use
        # assets_dir defaults to ~/.cache/mcbuilder/<mc_version>/
    """

    mc_version: str = "1.21.4"
    max_dimensions: tuple[int, int, int] = _DEFAULT_MAX_DIMENSIONS
    allowlist: list[str] = field(default_factory=list)
    assets_dir: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> "McbuildConfig":
        """Load configuration from a ``mcbuild.toml`` file.

        Missing keys fall back to defaults. Raises ``FileNotFoundError``
        when the file does not exist and ``ValueError`` on invalid content.
        """
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"mcbuild.toml not found: {path}")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"invalid TOML in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"invalid TOML in {path}: expected a table at top level")
        return cls._from_dict(data)

    @classmethod
    def find(cls, start: str | Path) -> "McbuildConfig | None":
        """Walk up from ``start`` (file or directory) to the filesystem root.

        Returns the first ``mcbuild.toml`` found, or ``None`` when there is
        no config file on the way up.
        """
        current = Path(start).resolve()
        if current.is_file():
            current = current.parent
        for directory in (current, *current.parents):
            candidate = directory / "mcbuild.toml"
            if candidate.is_file():
                return cls.load(candidate)
        return None

    @classmethod
    def _from_dict(cls, data: dict) -> "McbuildConfig":
        mc_version = data.get("mc_version", "1.21.4")
        if not isinstance(mc_version, str) or not mc_version:
            raise ValueError("mc_version must be a non-empty string")

        raw_dims = data.get("max_dimensions", list(_DEFAULT_MAX_DIMENSIONS))
        try:
            dims = tuple(int(d) for d in raw_dims)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"max_dimensions must be a list of 3 integers, got {raw_dims!r}"
            ) from exc
        if len(dims) != 3 or any(d <= 0 for d in dims):
            raise ValueError(
                f"max_dimensions must be 3 positive integers, got {raw_dims!r}"
            )

        allowlist = data.get("allowlist", [])
        if not isinstance(allowlist, list) or not all(
            isinstance(a, str) for a in allowlist
        ):
            raise ValueError(
                f"allowlist must be a list of strings, got {allowlist!r}"
            )

        assets_dir = data.get("assets_dir")
        if assets_dir is not None:
            if not isinstance(assets_dir, str):
                raise ValueError(
                    f"assets_dir must be a string path, got {assets_dir!r}"
                )
            assets_dir = Path(assets_dir).expanduser()

        return cls(
            mc_version=mc_version,
            max_dimensions=dims,  # type: ignore[arg-type]
            allowlist=list(allowlist),
            assets_dir=assets_dir,
        )

    def resolve_assets_dir(self) -> Path:
        """Effective assets directory.

        Uses ``assets_dir`` when set, otherwise
        ``~/.cache/mcbuilder/<mc_version>/``.
        """
        if self.assets_dir is not None:
            return self.assets_dir
        return Path.home() / ".cache" / "mcbuilder" / self.mc_version
