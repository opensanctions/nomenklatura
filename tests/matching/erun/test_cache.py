import json
from pathlib import Path

import numpy as np

from nomenklatura.matching.erun.cache import load_cache
from nomenklatura.matching.erun.build import (
    build_prepared_dataset,
    verify_cache,
)
from nomenklatura.matching.erun.evaluate import score_metrics
from nomenklatura.matching.erun.train import fit_cached_model


def entity(identifier: str, name: str) -> dict[str, object]:
    return {
        "id": identifier,
        "schema": "Person",
        "properties": {"name": [name]},
    }


def write_pairs(path: Path) -> None:
    records = [
        ("positive", "Alice One", "Alice One"),
        ("positive", "Bob Two", "Bob Two"),
        ("positive", "Carla Three", "Carla Three"),
        ("negative", "David Four", "Edith Five"),
        ("negative", "Frank Six", "Grace Seven"),
        ("negative", "Heidi Eight", "Ivan Nine"),
    ]
    with path.open("w") as fh:
        for index, (label, left_name, right_name) in enumerate(records):
            row = {
                "judgement": label,
                "left": entity(f"left-{index}", left_name),
                "right": entity(f"right-{index}", right_name),
            }
            fh.write(json.dumps(row))
            fh.write("\n")


def test_build_and_load_feature_cache(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    prepared_path = tmp_path / "prepared"
    write_pairs(pairs_path)
    build_prepared_dataset(
        pairs_file=pairs_path,
        output_dir=prepared_path,
        test_size=0.3,
        development_size=4,
        seed=42,
        workers=1,
        batch_size=2,
        force=False,
    )
    loaded_metadata, arrays = load_cache(prepared_path)

    assert loaded_metadata["rows"] == 6
    assert arrays["features"].shape == (6, 21)
    assert arrays["labels"].sum() == 3
    assert arrays["weights"].sum() == 6
    assert arrays["development"].sum() == 4
    verified = verify_cache(prepared_path, prepared_path / "manifest.jsonl")
    assert verified["counts"]["label:positive"] == 3
    assert verified["mismatches"] == {}


def test_score_metrics_handles_single_label_slice() -> None:
    labels = np.asarray([1, 1], dtype=np.uint8)
    scores = np.asarray([0.8, 0.9], dtype=np.float64)

    result = score_metrics(labels, scores, thresholds=[0.5])

    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["thresholds"]["0.5"] == {"precision": 1.0, "recall": 1.0}


def test_fit_cached_model_uses_only_train_partition(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    prepared_path = tmp_path / "prepared"
    write_pairs(pairs_path)
    build_prepared_dataset(
        pairs_file=pairs_path,
        output_dir=prepared_path,
        test_size=0.3,
        development_size=6,
        seed=42,
        workers=1,
        batch_size=2,
        force=False,
    )

    artifact, report = fit_cached_model(
        prepared_path,
        development_only=True,
        weight_mode="grouped",
        cv=2,
        n_jobs=1,
        max_iter=1_000,
    )

    assert report["groups"] == 4
    assert report["positive_groups"] == 2
    assert artifact["training"] == report
    assert list(artifact["coefficients"]) == list(report["coefficients"])
