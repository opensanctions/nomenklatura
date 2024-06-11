import logging
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
    caplog,
):
    resolver = Resolver[CompositeEntity]()
    store = MemoryStore(test_dataset, resolver)
    algorithm = RegressionV1()
    a = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "a",
            "schema": "Company",
            "properties": {
                "name": "The AAA Weapons and Munitions Factory Joint Stock Company",
                "address": "Moscow",
            },
        },
    )
    b = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "b",
            "schema": "Company",
            "properties": {
                "name": "The BBB Weapons and Munitions Factory Joint Stock Company",
                "address": "Moscow",
            },
        },
    )
    c = CompositeEntity.from_data(
        test_dataset,
        {
            "id": "c",
            "schema": "Company",
            "properties": {
                "name": "The AAA Weapons and Ammunition Factory Joint Stock Company",
                "address": "Moscow",
            },
        },
    )
    writer = store.writer()
    writer.add_entity(a)
    writer.add_entity(b)
    writer.add_entity(c)
    writer.flush()

    resolver.decide("a", "b", Judgement.NEGATIVE, user="test")

    with caplog.at_level(logging.INFO):
        xref(
            resolver,
            store,
            # Not the default, but easily gets the scores where this is a problem
            algorithm=RegressionV1,
            # Lower than usual just because we're testing with one dataset
            negative_check_threshold=0.6
        )
    logs = {r.message for r in caplog.records}

    assert "Potential conflict: b <> a for c" in logs
