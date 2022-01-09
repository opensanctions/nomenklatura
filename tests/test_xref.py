import pytest
from nomenklatura.resolver import Resolver
from nomenklatura.xref import xref


@pytest.mark.asyncio
async def test_xref_candidates(dindex):
    resolver = Resolver()
    await xref(dindex, resolver, dindex.loader._entities.values())
    candidates = list([c async for c in resolver.get_candidates(limit=20)])
    assert len(candidates) == 20
    for left_id, right_id, score in candidates:
        left = await dindex.loader.get_entity(left_id)
        right = await dindex.loader.get_entity(right_id)
        if left.caption == "Johanna Quandt":
            assert right.caption == "Frau Johanna Quandt"
        assert score > 0
