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


def test_resolver():
    resolver = Resolver()
    resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert Identifier.get("a2") in resolver.connected(Identifier.get("a1"))
    assert resolver.get_judgement("a1", "a2") == Judgement.POSITIVE
    resolver.decide("b1", "b2", Judgement.POSITIVE)
    assert resolver.get_judgement("a1", "b1") == Judgement.NO_JUDGEMENT
    resolver.decide("a2", "b2", Judgement.NEGATIVE)
    assert resolver.get_judgement("a2", "b2") == Judgement.NEGATIVE
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE
    resolver.suggest("a1", "b1", 7.0)
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE

    assert resolver.get_canonical("a1") == "a1"
    assert resolver.get_canonical("a2") == "a2"

    resolver.suggest("c1", "c2", 7.0)
    assert resolver.get_edge("c1", "c2").score == 7.0
    resolver.suggest("c1", "c2", 8.0)
    assert resolver.get_edge("c1", "c2").score == 8.0
    resolver.decide("c1", "c2", Judgement.POSITIVE)
    assert resolver.get_edge("c1", "c2").score is None


def test_resolver_store():
    resolver = Resolver()
    resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide("a2", "b2", Judgement.NEGATIVE)
    resolver.suggest("a1", "c1", 7.0)

    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        resolver.save(path)

        other = Resolver.load(path)
        assert len(other.edges) == len(resolver.edges)
        assert resolver.get_edge("a1", "c1").score == 7.0


def test_resolver_candidates():
    resolver = Resolver()
    resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide("a2", "b2", Judgement.NEGATIVE)
    resolver.suggest("a1", "b2", 7.0)
    resolver.suggest("a1", "c1", 5.0)
    resolver.suggest("a1", "d1", 4.0)

    candidates = list(resolver.get_candidates())
    assert len(candidates) == 2, candidates
    assert candidates[0][2] == 5.0, candidates
