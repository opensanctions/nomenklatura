#!/usr/bin/env python3
"""Evaluate an `er-unstable` pipeline against a prepared feature cache."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from numpy.typing import NDArray
from sklearn import metrics  # type: ignore
from sklearn.pipeline import Pipeline  # type: ignore

from nomenklatura.matching.erun.cache import load_cache
from nomenklatura.matching.erun.model import EntityResolveRegression


def score_metrics(
    labels: NDArray[np.uint8],
    scores: NDArray[np.float64],
    thresholds: list[float],
    sample_weight: NDArray[np.uint32] | None = None,
) -> dict[str, Any]:
    """Compute calibration, ranking, and explicit threshold metrics."""

    result: dict[str, Any] = {
        "rows": len(labels),
        "effective_rows": int(sample_weight.sum())
        if sample_weight is not None
        else len(labels),
        "positive_rate": float(np.average(labels, weights=sample_weight)),
        "log_loss": float(
            metrics.log_loss(labels, scores, sample_weight=sample_weight, labels=[0, 1])
        ),
        "brier_score": float(
            metrics.brier_score_loss(labels, scores, sample_weight=sample_weight)
        ),
        "average_precision": None,
        "roc_auc": None,
        "thresholds": {},
    }
    if len(np.unique(labels)) == 2:
        result["average_precision"] = float(
            metrics.average_precision_score(
                labels, scores, sample_weight=sample_weight
            )
        )
        result["roc_auc"] = float(
            metrics.roc_auc_score(labels, scores, sample_weight=sample_weight)
        )
    for threshold in thresholds:
        predicted = scores >= threshold
        result["thresholds"][str(threshold)] = {
            "precision": float(
                metrics.precision_score(
                    labels, predicted, sample_weight=sample_weight, zero_division=0
                )
            ),
            "recall": float(
                metrics.recall_score(
                    labels, predicted, sample_weight=sample_weight, zero_division=0
                )
            ),
        }
    return result


def load_pipeline(model_path: Path | None) -> tuple[Pipeline, str]:
    if model_path is None:
        pipeline, _ = EntityResolveRegression.load()
        return pipeline, str(EntityResolveRegression.MODEL_PATH)
    stored = pickle.loads(model_path.read_bytes())
    pipeline = stored["pipe"] if isinstance(stored, dict) else stored
    if not isinstance(pipeline, Pipeline):
        raise TypeError("Model artifact does not contain a scikit-learn Pipeline")
    return pipeline, str(model_path)


def evaluate(
    cache_dir: Path,
    model_path: Path | None,
    partition: str,
    development_only: bool,
    thresholds: list[float],
) -> dict[str, Any]:
    metadata, arrays = load_cache(cache_dir)
    mask = np.ones(metadata["rows"], dtype=bool)
    if partition != "all":
        mask &= arrays["partitions"] == (partition == "test")
    if development_only:
        mask &= arrays["development"] == 1
    if not mask.any():
        raise ValueError("Selection contains no rows")

    pipeline, model_name = load_pipeline(model_path)
    features = np.asarray(arrays["features"][mask])
    labels = np.asarray(arrays["labels"][mask], dtype=np.uint8)
    weights = np.asarray(arrays["weights"][mask], dtype=np.uint32)
    schema_codes = np.asarray(arrays["schemata"][mask], dtype=np.uint8)
    scores = np.asarray(pipeline.predict_proba(features)[:, 1], dtype=np.float64)

    result: dict[str, Any] = {
        "model": model_name,
        "cache_feature_signature": metadata["feature_signature"],
        "selection": {
            "partition": partition,
            "development_only": development_only,
        },
        "grouped": score_metrics(labels, scores, thresholds),
        "frequency_weighted": score_metrics(labels, scores, thresholds, weights),
        "schemata": {},
    }
    for code, schema in enumerate(metadata["schema_names"]):
        schema_mask = schema_codes == code
        if not schema_mask.any():
            continue
        result["schemata"][schema] = {
            "grouped": score_metrics(
                labels[schema_mask], scores[schema_mask], thresholds
            ),
            "frequency_weighted": score_metrics(
                labels[schema_mask],
                scores[schema_mask],
                thresholds,
                weights[schema_mask],
            ),
        }
    return result


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache_dir", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--partition", choices=("train", "test", "all"), default="test")
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.5, 0.7, 0.9])
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    report = evaluate(
        args.cache_dir,
        args.model,
        args.partition,
        args.development_only,
        args.thresholds,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")


if __name__ == "__main__":
    main()
