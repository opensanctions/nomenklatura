from nomenklatura.xref import xref
from nomenklatura.store import SimpleMemoryStore


def test_xref_candidates(dstore: SimpleMemoryStore):
    xref(dstore)
    view = dstore.default_view(external=True)
    candidates = list(dstore.resolver.get_candidates(limit=20))
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
