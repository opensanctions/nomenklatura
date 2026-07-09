#!/usr/bin/env python3
"""Build the prepared `er-unstable` training dataset from raw pair judgements."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np
from followthemoney import EntityProxy
from followthemoney.exc import InvalidData
from numpy.lib.format import open_memmap

from nomenklatura.judgement import Judgement
from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.pairs import JudgedPair

from nomenklatura.matching.erun.cache import (
    ARRAY_FILES,
    CACHE_FORMAT_VERSION,
    feature_signature,
    load_cache,
    sha256_file,
)


LABELS = (Judgement.POSITIVE, Judgement.NEGATIVE)

# The pair generator hashes decider identities; rule-based zavod/logic
# judgements are the one non-secret decider worth distinguishing, so their
# hash is recomputed here to track provenance per training group.
LOGIC_USER_HASH = hashlib.sha256(b"zavod/logic").hexdigest()[:12]


@dataclass
class ScanStats:
    """Track how raw rows are reduced to the population used for training."""

    raw_rows: int = 0
    skipped_judgement: int = 0
    skipped_invalid_schema_pair: int = 0
    skipped_nonmatchable: int = 0
    skipped_address: int = 0
    skipped_contradictory_cluster: int = 0
    skipped_cross_partition: int = 0
    eligible_rows: int = 0
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
            "eligible_rows": self.eligible_rows,
            "labels": dict(sorted(self.labels.items())),
            "schemata": dict(sorted(self.schemata.items())),
        }


@dataclass
class SnapshotGroup:
    """Represent rows that provide the matcher with identical observable input."""

    digest: str
    schema: str
    label_counts: Counter[str] = field(default_factory=Counter)
    representative_rows: dict[str, int] = field(default_factory=dict)
    partition_counts: Counter[str] = field(default_factory=Counter)
    logic_count: int = 0

    def add(self, label: str, row_number: int, partition: str, logic: bool) -> None:
        self.label_counts[label] += 1
        self.representative_rows.setdefault(label, row_number)
        self.partition_counts[partition] += 1
        if logic:
            self.logic_count += 1

    @property
    def contradictory(self) -> bool:
        return len(self.label_counts) > 1

    @property
    def split_ambiguous(self) -> bool:
        """Identical content observed on both sides of the cluster partition."""
        return len(self.partition_counts) > 1

    @property
    def count(self) -> int:
        return sum(self.label_counts.values())

    @property
    def label(self) -> str:
        if self.contradictory:
            raise ValueError("Contradictory snapshot group has no single label")
        return next(iter(self.label_counts))

    @property
    def partition(self) -> str:
        if self.split_ambiguous:
            raise ValueError("Split-ambiguous snapshot group has no partition")
        return next(iter(self.partition_counts))


@dataclass(frozen=True)
class ManifestRow:
    snapshot: str
    schema: str
    label: str
    count: int
    logic_count: int
    representative_row: int
    partition: str
    development: bool


@dataclass(frozen=True)
class PairRecord:
    """One raw pair row with the split and provenance context it carries."""

    row_number: int
    pair: JudgedPair
    left_cluster: str
    right_cluster: str
    user: str | None


def iter_eligible_pairs(path: Path, stats: ScanStats) -> Iterator[PairRecord]:
    """Yield exactly the pair population accepted by the current trainer."""

    with path.open() as fh:
        for row_number, line in enumerate(fh, 1):
            stats.raw_rows += 1
            data = json.loads(line)
            judgement = Judgement(data["judgement"])
            if judgement not in LABELS:
                stats.skipped_judgement += 1
                continue
            left = EntityProxy.from_dict(data["left"])
            right = EntityProxy.from_dict(data["right"])
            try:
                pair = JudgedPair(left, right, judgement)
            except InvalidData:
                stats.skipped_invalid_schema_pair += 1
                continue
            if not pair.left.schema.matchable or not pair.right.schema.matchable:
                stats.skipped_nonmatchable += 1
                continue
            if pair.left.schema.is_a("Address") or pair.right.schema.is_a("Address"):
                stats.skipped_address += 1
                continue
            try:
                left_cluster = data["left_cluster"]
                right_cluster = data["right_cluster"]
            except KeyError:
                raise ValueError(
                    f"Pair row {row_number} lacks cluster labels; the file "
                    "predates the matcher_training generator (see its DATA.md)."
                )
            stats.eligible_rows += 1
            stats.labels[judgement.value] += 1
            stats.schemata[pair.schema.name] += 1
            yield PairRecord(
                row_number=row_number,
                pair=pair,
                left_cluster=left_cluster,
                right_cluster=right_cluster,
                user=data.get("user"),
            )


def snapshot_digest(pair: JudgedPair) -> str:
    """Identify identical ordered model inputs without using canonical IDs."""

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


def cluster_partition(cluster: str, test_size: float, seed: int) -> str:
    """Assign a resolver cluster to a partition, statelessly and reproducibly.

    The cluster label is the split unit: a pair may only train or evaluate
    when both of its sides fall in the same partition, so no cluster's
    evidence ever appears on both sides of the split."""
    digest = hashlib.sha256(f"{seed}:{cluster}".encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    return "test" if fraction < test_size else "train"


def collect_snapshot_groups(
    path: Path, test_size: float, seed: int
) -> tuple[dict[str, SnapshotGroup], ScanStats]:
    """Collect compact snapshot metadata while streaming the raw pair file."""

    stats = ScanStats()
    groups: dict[str, SnapshotGroup] = {}
    for record in iter_eligible_pairs(path, stats):
        pair = record.pair
        if pair.judgement != Judgement.POSITIVE:
            if record.left_cluster == record.right_cluster:
                # The resolver graph contradicts itself: a non-positive
                # judgement between sides it also positively merged.
                stats.skipped_contradictory_cluster += 1
                continue
        left_part = cluster_partition(record.left_cluster, test_size, seed)
        right_part = cluster_partition(record.right_cluster, test_size, seed)
        if left_part != right_part:
            # The price of a leakage-free split: cross-partition pairs are
            # discarded rather than allowed to share cluster evidence.
            stats.skipped_cross_partition += 1
            continue
        digest = snapshot_digest(pair)
        group = groups.get(digest)
        if group is None:
            group = SnapshotGroup(digest=digest, schema=pair.schema.name)
            groups[digest] = group
        group.add(
            pair.judgement.value,
            record.row_number,
            left_part,
            record.user == LOGIC_USER_HASH,
        )
    return groups, stats


def snapshot_summary(
    groups: dict[str, SnapshotGroup], stats: ScanStats
) -> dict[str, Any]:
    """Summarize deduplication, contradictions and split losses for the report."""

    contradictory = [group for group in groups.values() if group.contradictory]
    ambiguous = [
        group
        for group in groups.values()
        if group.split_ambiguous and not group.contradictory
    ]
    clean = [
        group
        for group in groups.values()
        if not group.contradictory and not group.split_ambiguous
    ]
    grouped_rows = (
        stats.eligible_rows
        - stats.skipped_contradictory_cluster
        - stats.skipped_cross_partition
    )
    return {
        "format_version": 2,
        "scan": stats.to_dict(),
        "snapshots": {
            "unique": len(groups),
            "clean": len(clean),
            "contradictory": len(contradictory),
            "split_ambiguous": len(ambiguous),
            "grouped_rows": grouped_rows,
            "duplicate_rows_beyond_first": grouped_rows - len(groups),
            "quarantined_rows": sum(
                group.count for group in contradictory + ambiguous
            ),
        },
    }


def _sample_key(group: SnapshotGroup, seed: int) -> bytes:
    return hashlib.sha256(f"{seed}:{group.digest}".encode("ascii")).digest()


def select_development_groups(
    groups: list[SnapshotGroup], target_size: int, seed: int
) -> set[str]:
    """Select an approximately sized subset while preserving every stratum."""

    if target_size >= len(groups):
        return {group.digest for group in groups}
    strata: dict[tuple[str, str], list[SnapshotGroup]] = defaultdict(list)
    for group in groups:
        strata[(group.schema, group.label)].append(group)
    if target_size < len(strata):
        raise ValueError(
            f"Development size {target_size} cannot cover {len(strata)} strata"
        )

    total = len(groups)
    quotas: dict[tuple[str, str], int] = {}
    remainders: list[tuple[float, tuple[str, str]]] = []
    for stratum, members in strata.items():
        exact = target_size * len(members) / total
        quotas[stratum] = min(len(members), max(1, math.floor(exact)))
        remainders.append((exact - math.floor(exact), stratum))

    assigned = sum(quotas.values())
    if assigned > target_size:
        for _, stratum in sorted(remainders):
            if assigned <= target_size:
                break
            if quotas[stratum] > 1:
                quotas[stratum] -= 1
                assigned -= 1
    while assigned < target_size:
        changed = False
        for _, stratum in sorted(remainders, reverse=True):
            if quotas[stratum] < len(strata[stratum]):
                quotas[stratum] += 1
                assigned += 1
                changed = True
                if assigned == target_size:
                    break
        if not changed:
            break

    selected: set[str] = set()
    for stratum, members in strata.items():
        ordered = sorted(members, key=lambda group: _sample_key(group, seed))
        selected.update(group.digest for group in ordered[: quotas[stratum]])
    return selected


def write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for record in records:
            fh.write(json.dumps(record, sort_keys=True))
            fh.write("\n")


def prepare_manifest(
    pairs_file: Path,
    output_dir: Path,
    test_size: float,
    development_size: int,
    seed: int,
) -> dict[str, Any]:
    """Write the grouped manifest, quarantine, and preparation summary."""

    groups, stats = collect_snapshot_groups(pairs_file, test_size, seed)
    quarantined = [
        group
        for group in groups.values()
        if group.contradictory or group.split_ambiguous
    ]
    clean = [
        group
        for group in groups.values()
        if not group.contradictory and not group.split_ambiguous
    ]
    development = select_development_groups(clean, development_size, seed)

    manifest_records: Iterable[dict[str, Any]] = (
        {
            "snapshot": group.digest,
            "schema": group.schema,
            "label": group.label,
            "count": group.count,
            "logic_count": group.logic_count,
            "representative_row": group.representative_rows[group.label],
            "partition": group.partition,
            "development": group.digest in development,
        }
        for group in sorted(clean, key=lambda group: group.digest)
    )
    quarantine_records: Iterable[dict[str, Any]] = (
        {
            "snapshot": group.digest,
            "schema": group.schema,
            "reason": "labels" if group.contradictory else "partitions",
            "label_counts": dict(sorted(group.label_counts.items())),
            "representative_rows": dict(sorted(group.representative_rows.items())),
        }
        for group in sorted(quarantined, key=lambda group: group.digest)
    )
    write_jsonl(output_dir / "manifest.jsonl", manifest_records)
    write_jsonl(output_dir / "quarantine.jsonl", quarantine_records)

    report = snapshot_summary(groups, stats)
    partition_groups: Counter[str] = Counter()
    partition_rows: Counter[str] = Counter()
    logic_rows = 0
    development_strata: Counter[str] = Counter()
    for group in clean:
        partition_groups[group.partition] += 1
        partition_rows[group.partition] += group.count
        logic_rows += group.logic_count
        if group.digest in development:
            development_strata[f"{group.schema}:{group.label}"] += 1
    report["preparation"] = {
        "seed": seed,
        "test_size": test_size,
        "development_target": development_size,
        "development_groups": len(development),
        "development_strata": dict(sorted(development_strata.items())),
        "partition_groups": dict(sorted(partition_groups.items())),
        "partition_rows": dict(sorted(partition_rows.items())),
        "logic_rows": logic_rows,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        f"{json.dumps(report, indent=2, sort_keys=True)}\n"
    )
    return report


def read_manifest(path: Path) -> list[ManifestRow]:
    rows: list[ManifestRow] = []
    with path.open() as fh:
        for line in fh:
            rows.append(ManifestRow(**json.loads(line)))
    return rows


def encode_pair(item: tuple[int, JudgedPair]) -> tuple[int, list[float]]:
    index, pair = item
    return index, EntityResolveRegression.encode_pair(pair.left, pair.right)


def iter_selected_pairs(
    pairs_file: Path, row_to_index: dict[int, int]
) -> Iterator[tuple[int, JudgedPair]]:
    """Parse only manifest representatives; row numbers are line numbers, so
    eligibility does not need to be re-derived for the rows skipped here."""
    with pairs_file.open() as fh:
        for row_number, line in enumerate(fh, 1):
            index = row_to_index.get(row_number)
            if index is None:
                continue
            data = json.loads(line)
            pair = JudgedPair(
                EntityProxy.from_dict(data["left"]),
                EntityProxy.from_dict(data["right"]),
                Judgement(data["judgement"]),
            )
            yield index, pair


def iter_batches(
    values: Iterator[tuple[int, JudgedPair]], batch_size: int
) -> Iterator[list[tuple[int, JudgedPair]]]:
    batch: list[tuple[int, JudgedPair]] = []
    for value in values:
        batch.append(value)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def build_feature_cache(
    pairs_file: Path,
    manifest_path: Path,
    output_dir: Path,
    workers: int,
    batch_size: int,
) -> dict[str, object]:
    """Encode each manifest representative and write aligned cache arrays."""

    rows = read_manifest(manifest_path)
    if not rows:
        raise ValueError("Manifest is empty")
    row_to_index = {row.representative_row: index for index, row in enumerate(rows)}
    if len(row_to_index) != len(rows):
        raise ValueError("Manifest contains duplicate representative rows")

    output_dir.mkdir(parents=True, exist_ok=True)
    shape = (len(rows), len(EntityResolveRegression.FEATURES))
    features = open_memmap(
        output_dir / ARRAY_FILES["features"], mode="w+", dtype=np.float32, shape=shape
    )
    labels = np.asarray([row.label == "positive" for row in rows], dtype=np.uint8)
    weights = np.asarray([row.count for row in rows], dtype=np.uint32)
    logic_counts = np.asarray([row.logic_count for row in rows], dtype=np.uint32)
    schema_names = sorted({row.schema for row in rows})
    schema_codes = {schema: index for index, schema in enumerate(schema_names)}
    schemata = np.asarray([schema_codes[row.schema] for row in rows], dtype=np.uint8)
    partitions = np.asarray([row.partition == "test" for row in rows], dtype=np.uint8)
    development = np.asarray([row.development for row in rows], dtype=np.uint8)
    row_numbers = np.asarray([row.representative_row for row in rows], dtype=np.uint32)
    snapshots = np.asarray([row.snapshot.encode("ascii") for row in rows], dtype="S64")

    static_arrays: dict[str, np.ndarray[Any, Any]] = {
        "labels": labels,
        "weights": weights,
        "logic_counts": logic_counts,
        "schemata": schemata,
        "partitions": partitions,
        "development": development,
        "row_numbers": row_numbers,
        "snapshots": snapshots,
    }
    for name, array in static_arrays.items():
        np.save(output_dir / ARRAY_FILES[name], array, allow_pickle=False)

    started = time.monotonic()
    encoded = 0
    selected = iter_selected_pairs(pairs_file, row_to_index)
    if workers == 1:
        for batch in iter_batches(selected, batch_size):
            for index, values in map(encode_pair, batch):
                features[index] = values
                encoded += 1
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for batch in iter_batches(selected, batch_size):
                chunk_size = max(1, len(batch) // (workers * 4))
                for index, values in executor.map(
                    encode_pair, batch, chunksize=chunk_size
                ):
                    features[index] = values
                    encoded += 1
                if encoded and encoded % 10_000 < len(batch):
                    print(f"Encoded {encoded:,}/{len(rows):,} snapshots", flush=True)
    features.flush()
    if encoded != len(rows):
        raise ValueError(f"Encoded {encoded} representatives, expected {len(rows)}")

    metadata: dict[str, object] = {
        "format_version": CACHE_FORMAT_VERSION,
        "rows": len(rows),
        "feature_names": [
            feature.__name__ for feature in EntityResolveRegression.FEATURES
        ],
        "feature_signature": feature_signature(),
        "manifest_sha256": sha256_file(manifest_path),
        "schema_names": schema_names,
        "partition_codes": {"train": 0, "test": 1},
        "label_codes": {"negative": 0, "positive": 1},
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "workers": workers,
    }
    (output_dir / "cache.json").write_text(
        f"{json.dumps(metadata, indent=2, sort_keys=True)}\n"
    )
    return metadata


def verify_cache(cache_dir: Path, manifest_path: Path) -> dict[str, Any]:
    """Reject a cache unless every static array matches its manifest row."""

    metadata, arrays = load_cache(cache_dir)
    manifest_hash = sha256_file(manifest_path)
    if manifest_hash != metadata["manifest_sha256"]:
        raise ValueError("Manifest content does not match cache metadata")

    schema_codes = {
        name: index for index, name in enumerate(metadata["schema_names"])
    }
    counts: Counter[str] = Counter()
    mismatches: Counter[str] = Counter()
    with manifest_path.open() as fh:
        for index, line in enumerate(fh):
            row = json.loads(line)
            expected = {
                "labels": int(row["label"] == "positive"),
                "weights": row["count"],
                "logic_counts": row["logic_count"],
                "schemata": schema_codes[row["schema"]],
                "partitions": int(row["partition"] == "test"),
                "development": int(row["development"]),
                "row_numbers": row["representative_row"],
                "snapshots": row["snapshot"].encode("ascii"),
            }
            for name, value in expected.items():
                if arrays[name][index] != value:
                    mismatches[name] += 1
            counts["rows"] += 1
            counts[f"label:{row['label']}"] += 1
            counts[f"partition:{row['partition']}"] += 1
            counts["weighted_rows"] += row["count"]
            counts["development"] += int(row["development"])

    if counts["rows"] != metadata["rows"]:
        raise ValueError(
            f"Manifest contains {counts['rows']} rows, expected {metadata['rows']}"
        )
    if mismatches:
        raise ValueError(f"Cache arrays differ from manifest: {dict(mismatches)}")
    if not np.isfinite(arrays["features"]).all():
        raise ValueError("Feature matrix contains non-finite values")
    return {
        "manifest_sha256": manifest_hash,
        "counts": dict(sorted(counts.items())),
        "mismatches": {},
        "features_finite": True,
    }


def build_prepared_dataset(
    pairs_file: Path,
    output_dir: Path,
    test_size: float,
    development_size: int,
    seed: int,
    workers: int,
    batch_size: int,
    force: bool,
) -> dict[str, Any]:
    """Transform raw pair judgements into one verified prepared dataset bundle."""

    metadata_path = output_dir / "cache.json"
    if metadata_path.exists() and not force:
        raise FileExistsError(f"Prepared dataset already exists: {metadata_path}")
    started = time.monotonic()
    preparation = prepare_manifest(
        pairs_file=pairs_file,
        output_dir=output_dir,
        test_size=test_size,
        development_size=development_size,
        seed=seed,
    )
    cache_metadata = build_feature_cache(
        pairs_file=pairs_file,
        manifest_path=output_dir / "manifest.jsonl",
        output_dir=output_dir,
        workers=workers,
        batch_size=batch_size,
    )
    verification = verify_cache(output_dir, output_dir / "manifest.jsonl")
    report = {
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "preparation": preparation,
        "cache": cache_metadata,
        "verification": verification,
    }
    (output_dir / "build.json").write_text(
        f"{json.dumps(report, indent=2, sort_keys=True)}\n"
    )
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("pairs_file", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--test-size", type=float, default=0.30)
    parser.add_argument("--development-size", type=int, default=75_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if not 0.0 < args.test_size < 1.0:
        parser.error("--test-size must be between zero and one")
    if args.development_size < 1:
        parser.error("--development-size must be positive")
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    report = build_prepared_dataset(
        pairs_file=args.pairs_file,
        output_dir=args.output_dir,
        test_size=args.test_size,
        development_size=args.development_size,
        seed=args.seed,
        workers=args.workers,
        batch_size=args.batch_size,
        force=args.force,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
