#!/usr/bin/env python3
"""Train the packaged `er-unstable` model from a prepared feature cache."""

from __future__ import annotations

import argparse
import json
import os
import pickle
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from followthemoney.util import PathLike
from sklearn.linear_model import LogisticRegressionCV  # type: ignore
from sklearn.pipeline import Pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore

from nomenklatura.matching.erun.build import build_prepared_dataset
from nomenklatura.matching.erun.cache import load_cache
from nomenklatura.matching.erun.model import EntityResolveRegression


MODEL_FORMAT_VERSION = 1
RANDOM_SEED = 42


def make_model(cv: int, n_jobs: int, max_iter: int) -> Pipeline:
    """Build the CV-selected classifier used by the packaged ER model."""

    classifier = LogisticRegressionCV(
        Cs=10,
        l1_ratios=[0.0, 0.25, 0.5, 0.75, 1.0],
        solver="saga",
        scoring="neg_log_loss",
        cv=cv,
        max_iter=max_iter,
        random_state=RANDOM_SEED,
        n_jobs=n_jobs,
        use_legacy_attributes=False,
    )
    return Pipeline(
        [
            ("standardscaler", StandardScaler(with_mean=False)),
            ("logisticregressioncv", classifier),
        ]
    )


def fit_cached_model(
    cache_dir: Path,
    development_only: bool,
    weight_mode: str,
    cv: int,
    n_jobs: int,
    max_iter: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit the grouped train partition and return the model artifact plus report."""

    cache_metadata, arrays = load_cache(cache_dir)
    mask = arrays["partitions"] == 0
    if development_only:
        mask &= arrays["development"] == 1
    features = np.asarray(arrays["features"][mask])
    labels = np.asarray(arrays["labels"][mask], dtype=np.uint8)
    weights = np.asarray(arrays["weights"][mask], dtype=np.float64)
    if len(np.unique(labels)) != 2:
        raise ValueError("Training selection must contain both labels")
    sample_weight = weights if weight_mode == "frequency" else None

    pipeline = make_model(cv=cv, n_jobs=n_jobs, max_iter=max_iter)
    started = time.monotonic()
    fit_params: dict[str, Any] = {}
    if sample_weight is not None:
        fit_params["logisticregressioncv__sample_weight"] = sample_weight
    pipeline.fit(features, labels, **fit_params)
    elapsed = time.monotonic() - started

    classifier = pipeline.named_steps["logisticregressioncv"]
    coefficients = {
        feature.__name__: float(coefficient)
        for feature, coefficient in zip(
            EntityResolveRegression.FEATURES, classifier.coef_[0]
        )
    }
    report: dict[str, Any] = {
        "cache_feature_signature": cache_metadata["feature_signature"],
        "cache_manifest_sha256": cache_metadata["manifest_sha256"],
        "development_only": development_only,
        "weight_mode": weight_mode,
        "groups": len(labels),
        "represented_rows": int(weights.sum()),
        "positive_groups": int(labels.sum()),
        "positive_rate": float(labels.mean()),
        "weighted_positive_rate": float(np.average(labels, weights=weights)),
        "cv": cv,
        "selected_c": float(classifier.C_),
        "selected_l1_ratio": float(classifier.l1_ratio_),
        "iterations": np.asarray(classifier.n_iter_).tolist(),
        "elapsed_seconds": round(elapsed, 3),
        "coefficients": coefficients,
    }
    artifact = {
        "format_version": MODEL_FORMAT_VERSION,
        "pipe": pipeline,
        "coefficients": coefficients,
        "training": report,
    }
    return artifact, report


def write_model_artifact(
    artifact: dict[str, Any],
    report: dict[str, Any],
    output_model: Path,
) -> None:
    """Write an experimental model artifact and its JSON training report."""

    output_model.parent.mkdir(parents=True, exist_ok=True)
    output_model.write_bytes(pickle.dumps(artifact))
    report_path = output_model.with_suffix(f"{output_model.suffix}.json")
    report_path.write_text(f"{json.dumps(report, indent=2, sort_keys=True)}\n")


def train_cached_model(
    cache_dir: Path,
    output_model: Path,
    development_only: bool = False,
    weight_mode: str = "grouped",
    cv: int = 5,
    n_jobs: int = -1,
    max_iter: int = 2_000,
) -> dict[str, Any]:
    """Train from a prepared dataset directory and write a reusable artifact."""

    artifact, report = fit_cached_model(
        cache_dir=cache_dir,
        development_only=development_only,
        weight_mode=weight_mode,
        cv=cv,
        n_jobs=n_jobs,
        max_iter=max_iter,
    )
    write_model_artifact(artifact, report, output_model)
    return report


def train_matcher(pairs_file: PathLike) -> None:
    """Train and save the packaged ER model from raw pair judgements."""

    with tempfile.TemporaryDirectory(prefix="erun-training-") as tmpdir:
        cache_dir = Path(tmpdir) / "prepared"
        build_prepared_dataset(
            pairs_file=Path(pairs_file),
            output_dir=cache_dir,
            test_size=0.30,
            development_size=75_000,
            seed=RANDOM_SEED,
            workers=os.cpu_count() or 1,
            batch_size=10_000,
            force=True,
        )
        artifact, report = fit_cached_model(
            cache_dir=cache_dir,
            development_only=False,
            weight_mode="grouped",
            cv=5,
            n_jobs=-1,
            max_iter=2_000,
        )
    EntityResolveRegression.save(artifact["pipe"], artifact["coefficients"])
    print("Written to: %s" % EntityResolveRegression.MODEL_PATH.as_posix())
    print(json.dumps(report, indent=2, sort_keys=True))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache_dir", type=Path)
    parser.add_argument("output_model", type=Path)
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument(
        "--weight-mode", choices=("grouped", "frequency"), default="grouped"
    )
    parser.add_argument("--cv", type=int, default=5)
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument("--max-iter", type=int, default=2_000)
    args = parser.parse_args(argv)
    if args.cv < 2:
        parser.error("--cv must be at least two")
    if args.max_iter < 1:
        parser.error("--max-iter must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    report = train_cached_model(
        cache_dir=args.cache_dir,
        output_model=args.output_model,
        development_only=args.development_only,
        weight_mode=args.weight_mode,
        cv=args.cv,
        n_jobs=args.n_jobs,
        max_iter=args.max_iter,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
