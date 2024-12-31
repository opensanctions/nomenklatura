import re
from normality import collapse_spaces
from pathlib import Path

from nomenklatura.dataset.dataset import Dataset
from nomenklatura.entity import CompositeEntity
from nomenklatura.judgement import Judgement
from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.resolver import Resolver
from nomenklatura.store import SimpleMemoryStore
from nomenklatura.xref import xref


def test_xref_candidates(
    index_path: Path, resolver: Resolver[CompositeEntity], dstore: SimpleMemoryStore
):
    xref(resolver, dstore, index_path)
    view = dstore.default_view(external=True)
    candidates = list(resolver.get_candidates(limit=20))
    assert len(candidates) == 20
    for left_id, right_id, score in candidates:
        left = view.get_entity(left_id)
        right = view.get_entity(right_id)
        assert left is not None
        assert right is not None
        assert score is not None
        if left.caption == "Johanna Quandt":
            assert right.caption == "Frau Johanna Quandt"
        assert score > 0.0


def test_xref_potential_conflicts(
    index_path: Path,
    test_dataset: Dataset,
    resolver: Resolver[CompositeEntity],
    capsys,
):
    store = SimpleMemoryStore(test_dataset, resolver)
    a = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "a",
            "schema": "Company",
            "properties": {
                "name": ["The AAA Weapons and Munitions Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    b = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "b",
            "schema": "Company",
            "properties": {
                "name": ["The BBB Weapons and Munitions Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    c = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "c",
            "schema": "Company",
            "properties": {
                "name": ["The AAA Weapons and Ammunition Factory Joint Stock Company"],
                "address": ["Moscow"],
            },
        },
    )
    writer = store.writer()
    writer.add_entity(a)
    writer.add_entity(b)
    writer.add_entity(c)
    writer.flush()

    resolver.decide("a", "b", Judgement.NEGATIVE, user="test")

    xref(
        resolver,
        store,
        index_path,
        algorithm=RegressionV1,
        conflicting_match_threshold=0.9,
    )
    stdout = capsys.readouterr().out

    assert "Potential conflicting matches found:" in stdout, stdout
    assert "Candidate:\nc\n" in stdout, stdout
    flat = collapse_spaces(stdout)
    assert re.search(r"Left side of negative decision: (b|a)", flat), stdout
    assert re.search(r"Right side of negative decision: (b|a)", flat), stdout
    assert a.get("name")[0] in flat, stdout
    assert b.get("name")[0] in flat, stdout
    assert c.get("name")[0] in flat, stdout
