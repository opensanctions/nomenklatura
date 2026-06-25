"""Read and validate prepared `er-unstable` feature caches."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from nomenklatura.matching.erun.model import EntityResolveRegression


CACHE_FORMAT_VERSION = 1
ARRAY_FILES = {
    "features": "features.npy",
    "labels": "labels.npy",
    "weights": "weights.npy",
    "schemata": "schemata.npy",
    "partitions": "partitions.npy",
    "development": "development.npy",
    "row_numbers": "row_numbers.npy",
    "snapshots": "snapshots.npy",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def feature_signature() -> str:
    """Invalidate a cache when the encoder implementation or order changes."""

    digest = hashlib.sha256()
    directory = Path(__file__).parent
    for path in sorted(directory.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    for feature in EntityResolveRegression.FEATURES:
        digest.update(feature.__name__.encode("utf-8"))
    return digest.hexdigest()


def read_metadata(cache_dir: Path) -> dict[str, Any]:
    return json.loads((cache_dir / "cache.json").read_text())


def load_cache(
    cache_dir: Path, validate_features: bool = True
) -> tuple[dict[str, Any], dict[str, NDArray[Any]]]:
    """Load memory-mapped arrays and reject incomplete or stale caches."""

    metadata = read_metadata(cache_dir)
    if metadata.get("format_version") != CACHE_FORMAT_VERSION:
        raise ValueError("Unsupported feature cache format")
    expected_features = [feature.__name__ for feature in EntityResolveRegression.FEATURES]
    if metadata.get("feature_names") != expected_features:
        raise ValueError("Feature cache has a different feature order")
    if validate_features and metadata.get("feature_signature") != feature_signature():
        raise ValueError("Feature implementation changed; rebuild the cache")

    arrays = {
        name: np.load(cache_dir / filename, mmap_mode="r")
        for name, filename in ARRAY_FILES.items()
    }
    row_count = metadata["rows"]
    for name, array in arrays.items():
        if len(array) != row_count:
            raise ValueError(f"{name} contains {len(array)} rows, expected {row_count}")
    if arrays["features"].shape[1] != len(expected_features):
        raise ValueError("Feature matrix width does not match feature metadata")
    return metadata, arrays
