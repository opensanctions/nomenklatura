import warnings

from followthemoney.dataset.versions import Version, VersionHistory

warnings.warn(
    "nomenklatura.versions has moved to followthemoney.dataset.versions",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["Version", "VersionHistory"]
