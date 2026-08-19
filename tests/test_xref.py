import json
from pathlib import Path

from followthemoney import Dataset, StatementEntity

from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver
from nomenklatura.store import MemoryStore, SimpleMemoryStore, load_entity_file_store
from nomenklatura.xref import xref


def test_xref_candidates(
    index_path: Path,
    resolver: Resolver[StatementEntity],
    dstore: SimpleMemoryStore,
    db_session,
):
    xref(resolver, db_session, dstore, index_path)
    view = dstore.default_view(external=True)
    candidates = list(resolver.get_candidates(limit=20))
    assert len(candidates) == 20
    johanna_matches = []
    for left_id, right_id, score in candidates:
        left = view.get_entity(left_id)
        right = view.get_entity(right_id)
        assert left is not None
        assert right is not None
        assert score is not None
        assert score > 0.0
        if left.caption == "Johanna Quandt":
            johanna_matches.append((right.caption, score))
    # The best-scoring suggestion for Johanna Quandt is her own duplicate;
    # weaker same-surname pairs may also be suggested for review.
    assert johanna_matches
    best_caption, _ = max(johanna_matches, key=lambda m: m[1])
    assert best_caption == "Frau Johanna Quandt"


def test_xref_patience_ignores_decided_pairs(
    index_path: Path,
    resolver: Resolver[StatementEntity],
    db_session,
    tmp_path: Path,
):
    """Already-decided pairs at the top of the blocker ranking must not
    starve the patience counter before a genuine candidate is reached."""
    entities = []
    for idx in range(20):
        entities.append(
            {
                "id": f"noise-{idx}",
                "schema": "Company",
                "properties": {
                    "name": ["Global Trading House Alpha Beta Gamma Delta"],
                    "country": ["de"],
                },
            }
        )
    entities.append(
        {
            "id": "dupe-1",
            "schema": "Company",
            "properties": {"name": ["Zeta Petrochemical GmbH"]},
        }
    )
    entities.append(
        {
            "id": "dupe-2",
            "schema": "Company",
            "properties": {"name": ["Zeta Petrochemical"]},
        }
    )
    path = tmp_path / "patience.ijson"
    with open(path, "w") as fh:
        fh.writelines(json.dumps(entity) + "\n" for entity in entities)
    store = load_entity_file_store(path, resolver)

    # The noise entities out-rank the genuine pair on token overlap, and
    # every one of their 190 mutual pairs already carries a judgement.
    for left in range(20):
        for right in range(left + 1, 20):
            resolver.decide(f"noise-{left}", f"noise-{right}", Judgement.NEGATIVE)

    xref(
        resolver,
        db_session,
        store,
        index_path,
        limit=5,
        limit_factor=100,
        patience=30,
    )

    candidate_ids = set()
    for left_id, right_id, _ in resolver.get_candidates():
        candidate_ids.update((left_id, right_id))
    assert "dupe-1" in candidate_ids
    assert "dupe-2" in candidate_ids


def test_xref_skips_external_pairs(
    index_path: Path,
    resolver: Resolver[StatementEntity],
    db_session,
):
    """Two entities that are made up entirely of external statements must not be
    suggested against each other, but each must still be compared to real data."""
    dataset = Dataset.make({"name": "external_pairs"})
    store = MemoryStore(dataset, resolver)
    with store.writer() as writer:
        entities = (("ext-1", True), ("ext-2", True), ("int-1", False))
        for entity_id, external in entities:
            entity = StatementEntity(dataset, {"id": entity_id, "schema": "Company"})
            entity.add("name", "Zeta Petrochemical Holding", external=external)
            entity.add("country", "de", external=external)
            writer.add_entity(entity)

    xref(resolver, db_session, store, index_path)

    pairs = {frozenset((left, right)) for left, right, _ in resolver.get_candidates()}
    assert frozenset(("ext-1", "ext-2")) not in pairs
    assert frozenset(("int-1", "ext-1")) in pairs
    assert frozenset(("int-1", "ext-2")) in pairs
