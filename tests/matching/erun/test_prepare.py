import json
from pathlib import Path

import numpy as np
import pytest
from followthemoney import EntityProxy

from nomenklatura.judgement import Judgement
from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.erun.train import (
    build_dataset,
    cluster_partition,
    collect_snapshot_groups,
    fit_model,
    prepare_groups,
    score_metrics,
    snapshot_digest,
)
from nomenklatura.matching.pairs import JudgedPair

SEED = 42
TEST_SIZE = 0.3

TRAIN_CLUSTERS = [
    cluster
    for cluster in (f"cluster-{index}" for index in range(200))
    if cluster_partition(cluster, TEST_SIZE, SEED) == "train"
]
TEST_CLUSTERS = [
    cluster
    for cluster in (f"cluster-{index}" for index in range(200))
    if cluster_partition(cluster, TEST_SIZE, SEED) == "test"
]


def pair_row(
    index: int,
    label: str,
    left_name: str,
    right_name: str,
    left_cluster: str,
    right_cluster: str,
) -> dict[str, object]:
    return {
        "format_version": 1,
        "judgement": label,
        "left": {
            "id": f"left-{index}",
            "schema": "Person",
            "properties": {"name": [left_name]},
        },
        "right": {
            "id": f"right-{index}",
            "schema": "Person",
            "properties": {"name": [right_name]},
        },
        "left_cluster": left_cluster,
        "right_cluster": right_cluster,
    }


def write_pairs(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row))
            fh.write("\n")


def train_pairs() -> list[dict[str, object]]:
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
        pair_row(index, label, left, right, left_cluster, right_cluster)
        for index, (label, left, right, left_cluster, right_cluster) in enumerate(
            records
        )
    ]


def test_snapshot_digest_excludes_canonical_ids() -> None:
    left = EntityProxy.from_dict(
        {"id": "left-a", "schema": "Person", "properties": {"name": ["A"]}}
    )
    right = EntityProxy.from_dict(
        {"id": "right-a", "schema": "Person", "properties": {"name": ["B"]}}
    )
    same_left = EntityProxy.from_dict(
        {"id": "left-b", "schema": "Person", "properties": {"name": ["A"]}}
    )
    same_right = EntityProxy.from_dict(
        {"id": "right-b", "schema": "Person", "properties": {"name": ["B"]}}
    )
    pair = JudgedPair(left, right, Judgement.POSITIVE)
    same_pair = JudgedPair(same_left, same_right, Judgement.POSITIVE)
    reversed_pair = JudgedPair(right, left, Judgement.POSITIVE)

    assert snapshot_digest(pair) == snapshot_digest(same_pair)
    assert snapshot_digest(pair) != snapshot_digest(reversed_pair)


def test_cluster_partition_is_deterministic_and_proportional() -> None:
    labels = [f"c-{index}" for index in range(20_000)]
    first = [cluster_partition(label, 0.3, seed=1) for label in labels]
    second = [cluster_partition(label, 0.3, seed=1) for label in labels]
    other_seed = [cluster_partition(label, 0.3, seed=2) for label in labels]

    assert first == second
    assert first != other_seed
    assert 0.28 < first.count("test") / len(first) < 0.32


def test_input_format_is_explicit(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    row = pair_row(0, "positive", "A", "A", TRAIN_CLUSTERS[0], TRAIN_CLUSTERS[0])
    row["format_version"] = 2
    write_pairs(pairs_path, [row])

    with pytest.raises(ValueError, match="unsupported format_version"):
        collect_snapshot_groups(pairs_path)


def test_cross_partition_pairs_are_discarded(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    write_pairs(
        pairs_path,
        [
            pair_row(
                0,
                "negative",
                "Kept A",
                "Kept B",
                TRAIN_CLUSTERS[0],
                TRAIN_CLUSTERS[1],
            ),
            pair_row(
                1,
                "negative",
                "Cut A",
                "Cut B",
                TRAIN_CLUSTERS[2],
                TEST_CLUSTERS[0],
            ),
        ],
    )

    groups, stats = collect_snapshot_groups(pairs_path)

    assert stats.skipped_cross_partition == 1
    assert len(groups) == 1
    assert next(iter(groups.values())).partition == "train"


def test_same_cluster_negative_is_discarded(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    write_pairs(
        pairs_path,
        [
            pair_row(
                0,
                "negative",
                "Same A",
                "Same B",
                TRAIN_CLUSTERS[0],
                TRAIN_CLUSTERS[0],
            ),
            pair_row(
                1,
                "positive",
                "Same C",
                "Same C",
                TRAIN_CLUSTERS[1],
                TRAIN_CLUSTERS[1],
            ),
        ],
    )

    groups, stats = collect_snapshot_groups(pairs_path)

    assert stats.skipped_contradictory_cluster == 1
    assert len(groups) == 1


def test_conflicting_labels_exclude_snapshot(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    write_pairs(
        pairs_path,
        [
            pair_row(
                0,
                "positive",
                "Twin A",
                "Twin B",
                TRAIN_CLUSTERS[0],
                TRAIN_CLUSTERS[0],
            ),
            pair_row(
                1,
                "negative",
                "Twin A",
                "Twin B",
                TRAIN_CLUSTERS[1],
                TRAIN_CLUSTERS[2],
            ),
            pair_row(
                2,
                "positive",
                "Solo C",
                "Solo C",
                TRAIN_CLUSTERS[3],
                TRAIN_CLUSTERS[3],
            ),
        ],
    )

    groups, report = prepare_groups(pairs_path)

    assert len(groups) == 1
    assert report["snapshots"]["contradictory"] == 1
    assert groups[0].label == "positive"


def test_snapshots_seen_in_both_partitions_are_excluded(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    write_pairs(
        pairs_path,
        [
            pair_row(
                0,
                "negative",
                "Twin A",
                "Twin B",
                TRAIN_CLUSTERS[0],
                TRAIN_CLUSTERS[1],
            ),
            pair_row(
                1,
                "negative",
                "Twin A",
                "Twin B",
                TEST_CLUSTERS[0],
                TEST_CLUSTERS[1],
            ),
            pair_row(
                2,
                "positive",
                "Solo C",
                "Solo C",
                TRAIN_CLUSTERS[2],
                TRAIN_CLUSTERS[2],
            ),
        ],
    )

    groups, report = prepare_groups(pairs_path)

    assert len(groups) == 1
    assert report["snapshots"]["split_ambiguous"] == 1


def test_duplicate_snapshots_receive_one_vote(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    row = pair_row(
        0,
        "negative",
        "Twin A",
        "Twin B",
        TRAIN_CLUSTERS[0],
        TRAIN_CLUSTERS[1],
    )
    duplicate = dict(row)
    duplicate["user"] = "a-hashed-user"
    write_pairs(pairs_path, [row, duplicate])

    groups, report = prepare_groups(pairs_path)

    assert len(groups) == 1
    assert groups[0].count == 2
    assert report["snapshots"]["duplicate_rows_beyond_first"] == 1


def test_build_and_fit_use_cluster_partitions(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.jsonl"
    rows = train_pairs()
    rows.extend(
        [
            pair_row(
                6,
                "positive",
                "Nina Ten",
                "Nina Ten",
                TEST_CLUSTERS[0],
                TEST_CLUSTERS[0],
            ),
            pair_row(
                7,
                "negative",
                "Omar Eleven",
                "Pia Twelve",
                TEST_CLUSTERS[1],
                TEST_CLUSTERS[2],
            ),
        ]
    )
    write_pairs(pairs_path, rows)

    dataset = build_dataset(pairs_path, workers=1)
    _, coefficients, report = fit_model(dataset, cv=2, n_jobs=1, max_iter=1_000)

    assert dataset.features.shape == (8, 21)
    assert dataset.test_mask.sum() == 2
    assert report["groups"] == 6
    assert report["positive_groups"] == 3
    assert list(coefficients) == [
        feature.__name__ for feature in EntityResolveRegression.FEATURES
    ]


def test_score_metrics_handles_single_label_slice() -> None:
    labels = np.asarray([1, 1], dtype=np.uint8)
    scores = np.asarray([0.8, 0.9], dtype=np.float64)

    result = score_metrics(labels, scores, thresholds=(0.5,))

    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["thresholds"]["0.5"] == {"precision": 1.0, "recall": 1.0}
