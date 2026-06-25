from collections import Counter

from followthemoney import EntityProxy

from nomenklatura.judgement import Judgement
from nomenklatura.matching.pairs import JudgedPair

from nomenklatura.matching.erun.build import (
    SnapshotGroup,
    assign_partitions,
    select_development_groups,
    snapshot_digest,
)


def make_group(index: int, schema: str, label: str) -> SnapshotGroup:
    group = SnapshotGroup(digest=f"{index:064x}", schema=schema)
    group.add(label, index + 1)
    return group


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


def test_partitions_are_deterministic_and_stratified() -> None:
    groups = [
        *(make_group(i, "Person", "positive") for i in range(10)),
        *(make_group(i + 10, "Person", "negative") for i in range(4)),
        make_group(14, "Security", "positive"),
    ]

    first = assign_partitions(groups, test_size=0.3, seed=42)
    second = assign_partitions(reversed(groups), test_size=0.3, seed=42)

    assert first == second
    counts = Counter(
        (group.schema, group.label, first[group.digest]) for group in groups
    )
    assert counts[("Person", "positive", "test")] == 3
    assert counts[("Person", "negative", "test")] == 1
    assert counts[("Security", "positive", "train")] == 1


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
