import json
from pathlib import Path

import numpy as np

from nomenklatura.matching.erun.cache import load_cache
from nomenklatura.matching.erun.build import (
    LOGIC_USER_HASH,
    build_prepared_dataset,
    cluster_partition,
    verify_cache,
)
from nomenklatura.matching.erun.evaluate import score_metrics
from nomenklatura.matching.erun.train import fit_cached_model

SEED = 42
TEST_SIZE = 0.3

# Cluster labels with a known partition under the fixture seed, so the
# fixtures below control exactly which rows survive the cluster split.
TRAIN_CLUSTERS = [
    c
    for c in (f"cluster-{i}" for i in range(200))
    if cluster_partition(c, TEST_SIZE, SEED) == "train"
]
TEST_CLUSTERS = [
    c
    for c in (f"cluster-{i}" for i in range(200))
    if cluster_partition(c, TEST_SIZE, SEED) == "test"
]


def entity(identifier: str, name: str) -> dict[str, object]:
    return {
        "id": identifier,
        "schema": "Person",
        "properties": {"name": [name]},
    }


def pair_row(
    index: int,
    label: str,
    left_name: str,
    right_name: str,
    left_cluster: str,
    right_cluster: str,
    user: str = "abcdef123456",
) -> dict[str, object]:
    return {
        "judgement": label,
        "left": entity(f"left-{index}", left_name),
        "right": entity(f"right-{index}", right_name),
        "left_cluster": left_cluster,
        "right_cluster": right_cluster,
        "user": user,
    }


def write_pairs(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row))
            fh.write("\n")


def train_pairs() -> list[dict[str, object]]:
    """Six rows whose clusters all fall in the train partition."""
    train = TRAIN_CLUSTERS
    records = [
        ("positive", "Alice One", "Alice One", train[0], train[0]),
        ("positive", "Bob Two", "Bob Two", train[1], train[1]),
        ("positive", "Carla Three", "Carla Three", train[2], train[2]),
        ("negative", "David Four", "Edith Five", train[3], train[4]),
        ("negative", "Frank Six", "Grace Seven", train[5], train[6]),
        ("negative", "Heidi Eight", "Ivan Nine", train[7], train[8]),
    ]
    return [
        pair_row(index, label, left, right, lc, rc)
        for index, (label, left, right, lc, rc) in enumerate(records)
    ]


def test_build_and_load_feature_cache(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    prepared_path = tmp_path / "prepared"
    write_pairs(pairs_path, train_pairs())
    build_prepared_dataset(
        pairs_file=pairs_path,
        output_dir=prepared_path,
        test_size=TEST_SIZE,
        development_size=4,
        seed=SEED,
        workers=1,
        batch_size=2,
        force=False,
    )
    loaded_metadata, arrays = load_cache(prepared_path)

    assert loaded_metadata["rows"] == 6
    assert arrays["features"].shape == (6, 21)
    assert arrays["labels"].sum() == 3
    assert arrays["weights"].sum() == 6
    assert arrays["logic_counts"].sum() == 0
    assert arrays["development"].sum() == 4
    verified = verify_cache(prepared_path, prepared_path / "manifest.jsonl")
    assert verified["counts"]["label:positive"] == 3
    assert verified["mismatches"] == {}


def test_logic_provenance_is_tracked(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    prepared_path = tmp_path / "prepared"
    rows = train_pairs()
    # Repeat the first negative snapshot as a zavod/logic judgement: same
    # observable content, so it joins the same group and bumps logic_count.
    logic_row = dict(rows[3])
    logic_row["user"] = LOGIC_USER_HASH
    rows.append(logic_row)
    write_pairs(pairs_path, rows)
    build_prepared_dataset(
        pairs_file=pairs_path,
        output_dir=prepared_path,
        test_size=TEST_SIZE,
        development_size=4,
        seed=SEED,
        workers=1,
        batch_size=2,
        force=False,
    )
    _, arrays = load_cache(prepared_path)

    assert arrays["logic_counts"].sum() == 1
    grouped = np.flatnonzero(arrays["logic_counts"])
    assert arrays["weights"][grouped[0]] == 2


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
    rows = train_pairs()
    # Two extra rows that land wholly in the test partition.
    rows.append(
        pair_row(
            6, "positive", "Nina Ten", "Nina Ten", TEST_CLUSTERS[0], TEST_CLUSTERS[0]
        )
    )
    rows.append(
        pair_row(
            7,
            "negative",
            "Omar Eleven",
            "Pia Twelve",
            TEST_CLUSTERS[1],
            TEST_CLUSTERS[2],
        )
    )
    write_pairs(pairs_path, rows)
    build_prepared_dataset(
        pairs_file=pairs_path,
        output_dir=prepared_path,
        test_size=TEST_SIZE,
        development_size=8,
        seed=SEED,
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

    assert report["groups"] == 6
    assert report["positive_groups"] == 3
    assert artifact["training"] == report
    assert list(artifact["coefficients"]) == list(report["coefficients"])
