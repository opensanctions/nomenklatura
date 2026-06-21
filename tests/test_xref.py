from pathlib import Path
from followthemoney import StatementEntity

from nomenklatura.resolver import Resolver
from nomenklatura.store import SimpleMemoryStore
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
