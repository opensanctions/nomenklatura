import logging

from normality import collapse_spaces
from nomenklatura.dataset.dataset import Dataset
from nomenklatura.judgement import Judgement
from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.store.memory import MemoryStore
from nomenklatura.xref import xref
from nomenklatura.store import SimpleMemoryStore
from nomenklatura.resolver import Resolver
from nomenklatura.entity import CompositeEntity


def test_xref_candidates(
    dresolver: Resolver[CompositeEntity], dstore: SimpleMemoryStore
):
    xref(dresolver, dstore)
    view = dstore.default_view(external=True)
    candidates = list(dresolver.get_candidates(limit=20))
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
    test_dataset: Dataset,
    capsys,
):
    resolver = Resolver[CompositeEntity]()
    store = MemoryStore(test_dataset, resolver)
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
        algorithm=RegressionV1,
        conflicting_match_threshold=0.9,
    )
    stdout = capsys.readouterr().out

    assert "Potential conflicting matches found:" in stdout, stdout
    assert "Candidate:\nc\n" in stdout, stdout
    assert "Left side of negative decision:\nb\n" in stdout, stdout
    assert "Right side of negative decision:\na\n" in stdout, stdout
    flat = collapse_spaces(stdout)
    assert a.get("name")[0] in flat, flat
    assert b.get("name")[0] in flat, flat
    assert c.get("name")[0] in flat, flat
