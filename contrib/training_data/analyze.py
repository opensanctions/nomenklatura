#!/usr/bin/env python3
"""Analyze development errors and ambiguous evidence patterns."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from nomenklatura.matching.erun.cache import load_cache
from nomenklatura.matching.erun.evaluate import load_pipeline


def nonzero_features(names: list[str], values: np.ndarray[Any, Any]) -> dict[str, float]:
    return {
        names[index]: float(values[index]) for index in np.flatnonzero(values)
    }


def analyze(
    cache_dir: Path,
    model_path: Path | None,
    partition: str,
    development_only: bool,
    top_errors: int,
) -> dict[str, Any]:
    metadata, arrays = load_cache(cache_dir)
    mask = np.ones(metadata["rows"], dtype=bool)
    if partition != "all":
        mask &= arrays["partitions"] == (partition == "test")
    if development_only:
        mask &= arrays["development"] == 1
    pipeline, model_name = load_pipeline(model_path)
    features = np.asarray(arrays["features"][mask])
    labels = np.asarray(arrays["labels"][mask], dtype=np.uint8)
    schemata = np.asarray(arrays["schemata"][mask], dtype=np.uint8)
    weights = np.asarray(arrays["weights"][mask], dtype=np.uint32)
    rows = np.asarray(arrays["row_numbers"][mask], dtype=np.uint32)
    snapshots = np.asarray(arrays["snapshots"][mask])
    scores = np.asarray(pipeline.predict_proba(features)[:, 1], dtype=np.float64)
    clipped = np.clip(scores, 1e-15, 1 - 1e-15)
    losses = -(labels * np.log(clipped) + (1 - labels) * np.log(1 - clipped))

    schema_report: dict[str, Any] = {}
    for code, schema in enumerate(metadata["schema_names"]):
        selected = schemata == code
        if not selected.any():
            continue
        actual = float(labels[selected].mean())
        predicted = float(scores[selected].mean())
        schema_report[schema] = {
            "groups": int(selected.sum()),
            "represented_rows": int(weights[selected].sum()),
            "actual_positive_rate": actual,
            "mean_score": predicted,
            "calibration_bias": predicted - actual,
            "mean_log_loss": float(losses[selected].mean()),
        }

    error_records = []
    for index in np.argsort(losses)[-top_errors:][::-1]:
        error_records.append(
            {
                "schema": metadata["schema_names"][schemata[index]],
                "label": int(labels[index]),
                "score": float(scores[index]),
                "log_loss": float(losses[index]),
                "weight": int(weights[index]),
                "representative_row": int(rows[index]),
                "snapshot": snapshots[index].decode("ascii"),
                "features": nonzero_features(metadata["feature_names"], features[index]),
            }
        )

    vector_labels: dict[bytes, list[int]] = defaultdict(lambda: [0, 0])
    vector_examples: dict[bytes, int] = {}
    for index, values in enumerate(features):
        key = values.tobytes()
        vector_labels[key][labels[index]] += 1
        vector_examples.setdefault(key, index)
    ambiguous = [
        (counts[0] + counts[1], key, counts)
        for key, counts in vector_labels.items()
        if counts[0] and counts[1]
    ]
    ambiguous.sort(reverse=True, key=lambda item: item[0])
    ambiguous_records = []
    for total, key, counts in ambiguous[:top_errors]:
        index = vector_examples[key]
        ambiguous_records.append(
            {
                "groups": total,
                "negative": counts[0],
                "positive": counts[1],
                "features": nonzero_features(metadata["feature_names"], features[index]),
            }
        )

    scaler = pipeline.named_steps["standardscaler"]
    classifier = pipeline.named_steps["logisticregressioncv"]
    effective = classifier.coef_[0] / scaler.scale_
    coefficients = {
        name: float(coefficient)
        for name, coefficient in zip(metadata["feature_names"], effective)
    }
    return {
        "model": model_name,
        "selection": {
            "partition": partition,
            "development_only": development_only,
            "groups": len(labels),
        },
        "schemata": schema_report,
        "effective_coefficients": coefficients,
        "ambiguous_vectors": {
            "unique": len(ambiguous),
            "groups": sum(total for total, _, _ in ambiguous),
            "largest": ambiguous_records,
        },
        "worst_errors": error_records,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("cache_dir", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--partition", choices=("train", "test", "all"), default="test")
    parser.add_argument("--development-only", action="store_true")
    parser.add_argument("--top-errors", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.top_errors < 1:
        parser.error("--top-errors must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    report = analyze(
        args.cache_dir,
        args.model,
        args.partition,
        args.development_only,
        args.top_errors,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n")


if __name__ == "__main__":
    main()
