from nomenklatura.resolver import Resolver
from nomenklatura.xref import xref


def test_xref_candidates(dindex):
    resolver = Resolver()
    xref(dindex, resolver, dindex.loader)
    candidates = list(resolver.get_candidates(limit=20))
    assert len(candidates) == 20
    for left_id, right_id, score in candidates:
        left = dindex.loader.get_entity(left_id)
        right = dindex.loader.get_entity(right_id)
        if left.caption == "Johanna Quandt":
            assert right.caption == "Frau Johanna Quandt"
        assert score > 0
