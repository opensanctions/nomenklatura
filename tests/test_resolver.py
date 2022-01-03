import pytest
from pathlib import Path
from tempfile import NamedTemporaryFile
from followthemoney.dedupe.judgement import Judgement
from nomenklatura.resolver import Resolver, Identifier


def test_identifier():
    ident = Identifier.make()
    assert len(ident) > len(Identifier.PREFIX) + 5
    assert ident.id.startswith(Identifier.PREFIX)
    ident = Identifier.make("banana")
    assert ident.id == f"{Identifier.PREFIX}banana"


@pytest.mark.asyncio
async def test_resolver():
    resolver = Resolver()
    a_canon = await resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert a_canon.canonical, a_canon
    assert Identifier.get("a2") in resolver.connected(Identifier.get("a1"))
    assert resolver.get_judgement("a1", "a2") == Judgement.POSITIVE
    await resolver.decide("b1", "b2", Judgement.POSITIVE)
    assert resolver.get_judgement("a1", "b1") == Judgement.NO_JUDGEMENT
    await resolver.decide("a2", "b2", Judgement.NEGATIVE)
    assert resolver.get_judgement("a2", "b2") == Judgement.NEGATIVE
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE
    await resolver.suggest("a1", "b1", 7.0)
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE
    assert len(list(resolver.canonicals())) == 2, list(resolver.canonicals())

    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a2") == a_canon
    assert resolver.get_canonical("banana") == "banana"

    await resolver.decide("a1", "a17", Judgement.POSITIVE)
    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a17") == a_canon
    await resolver.decide("a1", "a0", Judgement.POSITIVE)
    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a0") == a_canon
    assert len(list(resolver.canonicals())) == 2, list(resolver.canonicals())

    await resolver.suggest("c1", "c2", 7.0)
    assert resolver.get_edge("c1", "c2").score == 7.0
    await resolver.suggest("c1", "c2", 8.0)
    assert resolver.get_edge("c1", "c2").score == 8.0
    ccn = await resolver.decide("c1", "c2", Judgement.POSITIVE)
    assert resolver.get_edge("c1", "c2") is None
    assert resolver.get_edge(ccn, "c2").score is None

    assert "a1" in resolver.get_referents(a_canon)
    assert ":memory:" in repr(resolver)

    resolver.explode("a1")
    assert resolver.get_canonical("a17") == "a17"
    assert resolver.get_judgement(a_canon, "a1") == Judgement.NO_JUDGEMENT
    assert resolver.get_judgement("b1", "b2") == Judgement.POSITIVE


@pytest.mark.asyncio
async def test_resolver_store():
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        resolver = Resolver(path)
        await resolver.decide("a1", "a2", Judgement.POSITIVE)
        await resolver.decide("a2", "b2", Judgement.NEGATIVE)
        await resolver.suggest("a1", "c1", 7.0)
        await resolver.save()

        other = await Resolver.load(path)
        assert len(other.edges) == len(resolver.edges)
        assert resolver.get_edge("a1", "c1").score == 7.0


@pytest.mark.asyncio
async def test_resolver_candidates():
    resolver = Resolver()
    await resolver.decide("a1", "a2", Judgement.POSITIVE)
    await resolver.decide("a2", "b2", Judgement.NEGATIVE)
    await resolver.suggest("a1", "b2", 7.0)
    await resolver.suggest("a1", "c1", 5.0)
    await resolver.suggest("a1", "d1", 4.0)

    candidates = list([c async for c in resolver.get_candidates()])
    assert len(candidates) == 2, candidates
    assert candidates[0][2] == 5.0, candidates

    resolver.prune()
    candidates = list([c async for c in resolver.get_candidates()])
    assert len(candidates) == 0, candidates
