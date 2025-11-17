from pathlib import Path
from followthemoney import StatementEntity

from nomenklatura.resolver import Resolver
from nomenklatura.store import SimpleMemoryStore
from nomenklatura.xref import xref


def test_xref_candidates(
    index_path: Path, resolver: Resolver[StatementEntity], dstore: SimpleMemoryStore
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
