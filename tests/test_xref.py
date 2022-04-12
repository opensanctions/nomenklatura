from nomenklatura.resolver import Resolver
from nomenklatura.xref import xref
from nomenklatura.loader import FileLoader


def test_xref_candidates(dloader: FileLoader):
    resolver = Resolver()
    xref(dloader, resolver)
    candidates = list(resolver.get_candidates(limit=20))
    assert len(candidates) == 20
    for left_id, right_id, score in candidates:
        left = dloader.get_entity(left_id)
        right = dloader.get_entity(right_id)
        if left.caption == "Johanna Quandt":
            assert right.caption == "Frau Johanna Quandt"
        assert score > 0
