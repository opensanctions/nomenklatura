import json
from pathlib import Path

from followthemoney import EntityProxy

from nomenklatura.judgement import Judgement
from nomenklatura.matching.pairs import JudgedPair

from nomenklatura.matching.erun.build import (
    SnapshotGroup,
    cluster_partition,
    collect_snapshot_groups,
    prepare_manifest,
    select_development_groups,
    snapshot_digest,
)

SEED = 42
TEST_SIZE = 0.3

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


def make_group(index: int, schema: str, label: str) -> SnapshotGroup:
    group = SnapshotGroup(digest=f"{index:064x}", schema=schema)
    group.add(label, index + 1, "train", logic=False)
    return group


def pair_row(
    label: str,
    left_name: str,
    right_name: str,
    left_cluster: str,
    right_cluster: str,
    user: str = "abcdef123456",
) -> dict[str, object]:
    return {
        "judgement": label,
        "left": {
            "id": f"l-{left_name}",
            "schema": "Person",
            "properties": {"name": [left_name]},
        },
        "right": {
            "id": f"r-{right_name}",
            "schema": "Person",
            "properties": {"name": [right_name]},
        },
        "left_cluster": left_cluster,
        "right_cluster": right_cluster,
        "user": user,
    }


def write_pairs(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row))
            fh.write("\n")


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
    labels = [f"c-{i}" for i in range(20_000)]
    first = [cluster_partition(label, 0.3, seed=1) for label in labels]
    second = [cluster_partition(label, 0.3, seed=1) for label in labels]
    other_seed = [cluster_partition(label, 0.3, seed=2) for label in labels]

    assert first == second
    assert first != other_seed
    test_share = first.count("test") / len(first)
    assert 0.28 < test_share < 0.32


def test_cross_partition_pairs_are_discarded(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    write_pairs(
        pairs_path,
        [
            pair_row(
                "negative", "Kept A", "Kept B", TRAIN_CLUSTERS[0], TRAIN_CLUSTERS[1]
            ),
            pair_row(
                "negative", "Cut A", "Cut B", TRAIN_CLUSTERS[2], TEST_CLUSTERS[0]
            ),
        ],
    )
    groups, stats = collect_snapshot_groups(pairs_path, TEST_SIZE, SEED)

    assert stats.skipped_cross_partition == 1
    assert len(groups) == 1
    assert next(iter(groups.values())).partition == "train"


def test_contradictory_cluster_pairs_are_skipped(tmp_path: Path) -> None:
    # A negative judgement whose two sides share one positive cluster is a
    # resolver self-contradiction and must not become training data.
    pairs_path = tmp_path / "pairs.json"
    write_pairs(
        pairs_path,
        [
            pair_row(
                "negative", "Same A", "Same B", TRAIN_CLUSTERS[0], TRAIN_CLUSTERS[0]
            ),
            pair_row(
                "positive", "Same C", "Same C", TRAIN_CLUSTERS[1], TRAIN_CLUSTERS[1]
            ),
        ],
    )
    groups, stats = collect_snapshot_groups(pairs_path, TEST_SIZE, SEED)

    assert stats.skipped_contradictory_cluster == 1
    assert len(groups) == 1
    assert next(iter(groups.values())).label == "positive"


def test_contradictory_labels_are_quarantined(tmp_path: Path) -> None:
    pairs_path = tmp_path / "pairs.json"
    prepared = tmp_path / "prepared"
    rows = [
        pair_row("positive", "Twin A", "Twin B", TRAIN_CLUSTERS[0], TRAIN_CLUSTERS[0]),
        pair_row("negative", "Twin A", "Twin B", TRAIN_CLUSTERS[1], TRAIN_CLUSTERS[2]),
        pair_row("positive", "Solo C", "Solo C", TRAIN_CLUSTERS[3], TRAIN_CLUSTERS[3]),
    ]
    write_pairs(pairs_path, rows)
    report = prepare_manifest(
        pairs_file=pairs_path,
        output_dir=prepared,
        test_size=TEST_SIZE,
        development_size=1,
        seed=SEED,
    )

    assert report["snapshots"]["contradictory"] == 1
    assert report["snapshots"]["clean"] == 1
    quarantined = [
        json.loads(line)
        for line in (prepared / "quarantine.jsonl").read_text().splitlines()
    ]
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "labels"
    assert quarantined[0]["label_counts"] == {"negative": 1, "positive": 1}
    manifest = [
        json.loads(line)
        for line in (prepared / "manifest.jsonl").read_text().splitlines()
    ]
    assert len(manifest) == 1
    assert manifest[0]["label"] == "positive"
    assert manifest[0]["logic_count"] == 0


def test_split_ambiguous_groups_are_quarantined(tmp_path: Path) -> None:
    # Identical observable content seen in both partitions cannot pick a side
    # without leaking; it is quarantined with its own reason.
    pairs_path = tmp_path / "pairs.json"
    prepared = tmp_path / "prepared"
    rows = [
        pair_row("negative", "Twin A", "Twin B", TRAIN_CLUSTERS[0], TRAIN_CLUSTERS[1]),
        pair_row("negative", "Twin A", "Twin B", TEST_CLUSTERS[0], TEST_CLUSTERS[1]),
        pair_row("positive", "Solo C", "Solo C", TRAIN_CLUSTERS[2], TRAIN_CLUSTERS[2]),
    ]
    write_pairs(pairs_path, rows)
    report = prepare_manifest(
        pairs_file=pairs_path,
        output_dir=prepared,
        test_size=TEST_SIZE,
        development_size=1,
        seed=SEED,
    )

    assert report["snapshots"]["split_ambiguous"] == 1
    assert report["snapshots"]["clean"] == 1
    quarantined = [
        json.loads(line)
        for line in (prepared / "quarantine.jsonl").read_text().splitlines()
    ]
    assert len(quarantined) == 1
    assert quarantined[0]["reason"] == "partitions"


def test_development_selection_preserves_each_stratum() -> None:
    groups = [
        *(make_group(i, "Person", "positive") for i in range(20)),
        *(make_group(i + 20, "Person", "negative") for i in range(8)),
        make_group(28, "Security", "positive"),
        make_group(29, "Security", "negative"),
    ]

    selected = select_development_groups(groups, target_size=10, seed=42)
    strata = {
        (group.schema, group.label)
        for group in groups
        if group.digest in selected
    }

    assert len(selected) == 10
    assert strata == {
        ("Person", "positive"),
        ("Person", "negative"),
        ("Security", "positive"),
        ("Security", "negative"),
    }
