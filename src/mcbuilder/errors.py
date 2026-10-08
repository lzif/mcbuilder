"""Shared exception hierarchy for mcbuilder."""


class McbuilderError(Exception):
    """Base class for all mcbuilder errors."""


class RegistryError(McbuilderError):
    """Raised when the block registry cannot be loaded or used."""


class AssetError(McbuilderError):
    """Raised when asset fetching fails."""
