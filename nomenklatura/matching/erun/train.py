"""Train the packaged `er-unstable` model from resolver judgement pairs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from followthemoney import EntityProxy
from followthemoney.exc import InvalidData
from followthemoney.util import PathLike
from numpy.typing import NDArray
from sklearn import metrics  # type: ignore
from sklearn.linear_model import LogisticRegressionCV  # type: ignore
from sklearn.pipeline import Pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore

from nomenklatura.judgement import Judgement
from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.pairs import JudgedPair

log = logging.getLogger(__name__)

FORMAT_VERSION = 1
RANDOM_SEED = 42
TEST_SIZE = 0.30
THRESHOLDS = (0.5, 0.7, 0.9)
LABELS = (Judgement.POSITIVE, Judgement.NEGATIVE)


@dataclass
class ScanStats:
    """Explain how raw generator rows become model inputs."""

    raw_rows: int = 0
    skipped_judgement: int = 0
    skipped_invalid_schema_pair: int = 0
    skipped_nonmatchable: int = 0
    skipped_address: int = 0
    skipped_contradictory_cluster: int = 0
    skipped_cross_partition: int = 0
    accepted_rows: int = 0
    labels: Counter[str] = field(default_factory=Counter)
    schemata: Counter[str] = field(default_factory=Counter)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_rows": self.raw_rows,
            "skipped_judgement": self.skipped_judgement,
            "skipped_invalid_schema_pair": self.skipped_invalid_schema_pair,
            "skipped_nonmatchable": self.skipped_nonmatchable,
            "skipped_address": self.skipped_address,
            "skipped_contradictory_cluster": self.skipped_contradictory_cluster,
            "skipped_cross_partition": self.skipped_cross_partition,
            "accepted_rows": self.accepted_rows,
            "labels": dict(sorted(self.labels.items())),
            "schemata": dict(sorted(self.schemata.items())),
        }


@dataclass
class SnapshotGroup:
    """Collect rows that present identical ordered evidence to the matcher."""

    digest: str
    schema: str
    label_counts: Counter[str] = field(default_factory=Counter)
    representative_rows: dict[str, int] = field(default_factory=dict)
    partitions: set[str] = field(default_factory=set)

    def add(self, label: str, row_number: int, partition: str) -> None:
        self.label_counts[label] += 1
        self.representative_rows.setdefault(label, row_number)
        self.partitions.add(partition)

    @property
    def count(self) -> int:
        return sum(self.label_counts.values())

    @property
    def contradictory(self) -> bool:
        return len(self.label_counts) > 1

    @property
    def split_ambiguous(self) -> bool:
        return len(self.partitions) > 1

    @property
    def label(self) -> str:
        if self.contradictory:
            raise ValueError("A contradictory snapshot has no single label")
        return next(iter(self.label_counts))

    @property
    def partition(self) -> str:
        if self.split_ambiguous:
            raise ValueError("A split-ambiguous snapshot has no partition")
        return next(iter(self.partitions))

    @property
    def representative_row(self) -> int:
        return self.representative_rows[self.label]


@dataclass(frozen=True)
class PreparedDataset:
    """Keep the arrays needed to fit and evaluate one model candidate."""

    features: NDArray[np.float32]
    labels: NDArray[np.uint8]
    test_mask: NDArray[np.bool_]
    schemata: NDArray[np.uint8]
    schema_names: list[str]
    report: dict[str, Any]


def cluster_partition(cluster: str, test_size: float, seed: int) -> str:
    """Assign all evidence for a resolver cluster to one stable partition."""

    digest = hashlib.sha256(f"{seed}:{cluster}".encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return "test" if fraction < test_size else "train"


def snapshot_digest(pair: JudgedPair) -> str:
    """Group identical matcher inputs without treating canonical IDs as identity."""

    payload = (
        pair.left.schema.name,
        pair.left.to_dict().get("properties", {}),
        pair.right.schema.name,
        pair.right.to_dict().get("properties", {}),
    )
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_pair(data: dict[str, Any]) -> JudgedPair:
    judgement = Judgement(data["judgement"])
    left = EntityProxy.from_dict(data["left"])
    right = EntityProxy.from_dict(data["right"])
    return JudgedPair(left, right, judgement)


def collect_snapshot_groups(
    path: Path, test_size: float = TEST_SIZE, seed: int = RANDOM_SEED
) -> tuple[dict[str, SnapshotGroup], ScanStats]:
    """Apply the generator contract and collect one group per observable pair."""

    stats = ScanStats()
    groups: dict[str, SnapshotGroup] = {}
    with path.open() as fh:
        for row_number, line in enumerate(fh, 1):
            stats.raw_rows += 1
            data: dict[str, Any] = json.loads(line)
            if data.get("format_version") != FORMAT_VERSION:
                raise ValueError(
                    f"Pair row {row_number} has unsupported format_version "
                    f"{data.get('format_version')!r}; expected {FORMAT_VERSION}"
                )
            try:
                judgement = Judgement(data["judgement"])
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f"Pair row {row_number} has no valid judgement"
                ) from exc
            if judgement not in LABELS:
                stats.skipped_judgement += 1
                continue
            try:
                pair = _read_pair(data)
            except (InvalidData, KeyError, TypeError, ValueError):
                stats.skipped_invalid_schema_pair += 1
                continue
            if not pair.left.schema.matchable or not pair.right.schema.matchable:
                stats.skipped_nonmatchable += 1
                continue
            if pair.left.schema.is_a("Address") or pair.right.schema.is_a("Address"):
                stats.skipped_address += 1
                continue
            try:
                left_cluster = str(data["left_cluster"])
                right_cluster = str(data["right_cluster"])
            except KeyError as exc:
                raise ValueError(
                    f"Pair row {row_number} lacks cluster labels from matcher_training"
                ) from exc
            if judgement != Judgement.POSITIVE and left_cluster == right_cluster:
                stats.skipped_contradictory_cluster += 1
                continue
            left_partition = cluster_partition(left_cluster, test_size, seed)
            right_partition = cluster_partition(right_cluster, test_size, seed)
            if left_partition != right_partition:
                stats.skipped_cross_partition += 1
                continue

            digest = snapshot_digest(pair)
            group = groups.get(digest)
            if group is None:
                group = SnapshotGroup(digest=digest, schema=pair.schema.name)
                groups[digest] = group
            group.add(judgement.value, row_number, left_partition)
            stats.accepted_rows += 1
            stats.labels[judgement.value] += 1
            stats.schemata[pair.schema.name] += 1
    return groups, stats


def prepare_groups(
    path: Path, test_size: float = TEST_SIZE, seed: int = RANDOM_SEED
) -> tuple[list[SnapshotGroup], dict[str, Any]]:
    """Select deterministic, non-contradictory groups for fitting and evaluation."""

    groups, stats = collect_snapshot_groups(path, test_size=test_size, seed=seed)
    contradictory = [group for group in groups.values() if group.contradictory]
    split_ambiguous = [
        group
        for group in groups.values()
        if group.split_ambiguous and not group.contradictory
    ]
    selected = sorted(
        (
            group
            for group in groups.values()
            if not group.contradictory and not group.split_ambiguous
        ),
        key=lambda group: group.digest,
    )
    partitions = Counter(group.partition for group in selected)
    report = {
        "format_version": FORMAT_VERSION,
        "seed": seed,
        "test_size": test_size,
        "scan": stats.to_dict(),
        "snapshots": {
            "observed": len(groups),
            "selected": len(selected),
            "train": partitions["train"],
            "test": partitions["test"],
            "contradictory": len(contradictory),
            "split_ambiguous": len(split_ambiguous),
            "duplicate_rows_beyond_first": stats.accepted_rows - len(groups),
            "quarantined_rows": sum(
                group.count for group in contradictory + split_ambiguous
            ),
        },
    }
    return selected, report


def _iter_representatives(
    path: Path, row_to_index: dict[int, int]
) -> Iterator[tuple[int, JudgedPair]]:
    with path.open() as fh:
        for row_number, line in enumerate(fh, 1):
            index = row_to_index.get(row_number)
            if index is None:
                continue
            data: dict[str, Any] = json.loads(line)
            yield index, _read_pair(data)


def _encode_pair(item: tuple[int, JudgedPair]) -> tuple[int, list[float]]:
    index, pair = item
    return index, EntityResolveRegression.encode_pair(pair.left, pair.right)


def build_dataset(
    pairs_file: PathLike,
    test_size: float = TEST_SIZE,
    seed: int = RANDOM_SEED,
    workers: int | None = None,
) -> PreparedDataset:
    """Build the in-memory arrays used for one transparent training run."""

    path = Path(pairs_file)
    groups, report = prepare_groups(path, test_size=test_size, seed=seed)
    if not groups:
        raise ValueError("Training selection contains no snapshot groups")
    row_to_index = {
        group.representative_row: index for index, group in enumerate(groups)
    }
    if len(row_to_index) != len(groups):
        raise ValueError("Snapshot groups share a representative input row")

    features = np.empty(
        (len(groups), len(EntityResolveRegression.FEATURES)), dtype=np.float32
    )
    selected = _iter_representatives(path, row_to_index)
    worker_count = workers if workers is not None else os.cpu_count() or 1
    started = time.monotonic()
    encoded = 0
    if worker_count == 1:
        results = map(_encode_pair, selected)
        for index, values in results:
            features[index] = values
            encoded += 1
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            for index, values in executor.map(_encode_pair, selected, chunksize=1_000):
                features[index] = values
                encoded += 1
                if encoded % 10_000 == 0:
                    log.info("Encoded %d/%d snapshots", encoded, len(groups))
    if encoded != len(groups):
        raise ValueError(f"Encoded {encoded} snapshots, expected {len(groups)}")

    schema_names = sorted({group.schema for group in groups})
    schema_codes = {name: index for index, name in enumerate(schema_names)}
    labels = np.asarray(
        [group.label == Judgement.POSITIVE.value for group in groups], dtype=np.uint8
    )
    test_mask = np.asarray(
        [group.partition == "test" for group in groups], dtype=np.bool_
    )
    schemata = np.asarray(
        [schema_codes[group.schema] for group in groups], dtype=np.uint8
    )
    report["encoding"] = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "features": len(EntityResolveRegression.FEATURES),
        "workers": worker_count,
    }
    return PreparedDataset(
        features=features,
        labels=labels,
        test_mask=test_mask,
        schemata=schemata,
        schema_names=schema_names,
        report=report,
    )


def make_model(cv: int = 5, n_jobs: int = -1, max_iter: int = 2_000) -> Pipeline:
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


def fit_model(
    dataset: PreparedDataset,
    cv: int = 5,
    n_jobs: int = -1,
    max_iter: int = 2_000,
) -> tuple[Pipeline, dict[str, float], dict[str, Any]]:
    """Fit equal-weight snapshot groups from the training partition."""

    train_mask = ~dataset.test_mask
    features = dataset.features[train_mask]
    labels = dataset.labels[train_mask]
    if len(np.unique(labels)) != 2:
        raise ValueError("Training partition must contain both labels")

    pipeline = make_model(cv=cv, n_jobs=n_jobs, max_iter=max_iter)
    started = time.monotonic()
    pipeline.fit(features, labels)
    elapsed = time.monotonic() - started
    classifier = pipeline.named_steps["logisticregressioncv"]
    coefficients = {
        feature.__name__: float(coefficient)
        for feature, coefficient in zip(
            EntityResolveRegression.FEATURES, classifier.coef_[0]
        )
    }
    report = {
        "groups": len(labels),
        "positive_groups": int(labels.sum()),
        "positive_rate": float(labels.mean()),
        "cv": cv,
        "selected_c": float(np.asarray(classifier.C_).item()),
        "selected_l1_ratio": float(np.asarray(classifier.l1_ratio_).item()),
        "iterations": np.asarray(classifier.n_iter_).tolist(),
        "elapsed_seconds": round(elapsed, 3),
        "coefficients": coefficients,
    }
    return pipeline, coefficients, report


def score_metrics(
    labels: NDArray[np.uint8],
    scores: NDArray[np.float64],
    thresholds: tuple[float, ...] = THRESHOLDS,
) -> dict[str, Any]:
    """Report calibration, ranking, and threshold behavior for one slice."""

    result: dict[str, Any] = {
        "groups": len(labels),
        "positive_rate": float(labels.mean()),
        "log_loss": float(metrics.log_loss(labels, scores, labels=[0, 1])),
        "brier_score": float(metrics.brier_score_loss(labels, scores)),
        "average_precision": None,
        "roc_auc": None,
        "thresholds": {},
    }
    if len(np.unique(labels)) == 2:
        result["average_precision"] = float(
            metrics.average_precision_score(labels, scores)
        )
        result["roc_auc"] = float(metrics.roc_auc_score(labels, scores))
    for threshold in thresholds:
        predicted = scores >= threshold
        result["thresholds"][str(threshold)] = {
            "precision": float(
                metrics.precision_score(labels, predicted, zero_division=0)
            ),
            "recall": float(metrics.recall_score(labels, predicted, zero_division=0)),
        }
    return result


def evaluate_model(dataset: PreparedDataset, pipeline: Pipeline) -> dict[str, Any]:
    """Evaluate a candidate only on the cluster-disjoint test partition."""

    mask = dataset.test_mask
    if not mask.any():
        raise ValueError("Test partition contains no snapshot groups")
    features = dataset.features[mask]
    labels = dataset.labels[mask]
    schemata = dataset.schemata[mask]
    scores = np.asarray(pipeline.predict_proba(features)[:, 1], dtype=np.float64)
    by_schema: dict[str, Any] = {}
    for code, schema in enumerate(dataset.schema_names):
        schema_mask = schemata == code
        if schema_mask.any():
            by_schema[schema] = score_metrics(labels[schema_mask], scores[schema_mask])
    return {
        "grouped": score_metrics(labels, scores),
        "schemata": by_schema,
    }


def train_matcher(pairs_file: PathLike) -> None:
    """Train and save the production model from matcher_training output."""

    dataset = build_dataset(pairs_file)
    pipeline, coefficients, training = fit_model(dataset)
    evaluation = evaluate_model(dataset, pipeline)
    EntityResolveRegression.save(pipeline, coefficients)
    report = {
        "model": str(EntityResolveRegression.MODEL_PATH),
        "dataset": dataset.report,
        "training": training,
        "evaluation": evaluation,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
