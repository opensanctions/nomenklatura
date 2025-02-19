from pathlib import Path
from tempfile import NamedTemporaryFile

from nomenklatura import settings
from nomenklatura.db import get_engine, get_metadata
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Resolver, Identifier
from nomenklatura.resolver.edge import Edge
from nomenklatura.statement import Statement


def test_identifier():
    ident = Identifier.make()
    assert len(ident) > len(Identifier.PREFIX) + 5
    assert ident.id.startswith(Identifier.PREFIX)
    ident = Identifier.make("banana")
    assert ident.id == f"{Identifier.PREFIX}banana"


def test_qid_identifier():
    ident_low = Identifier("Q3481")
    ident_hi = Identifier("Q63481")
    assert ident_low.id == "Q3481"
    assert ident_hi.id == "Q63481"


def test_resolver(resolver):
    resolver.begin()
    a_canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert a_canon.canonical, a_canon
    assert Identifier.get("a2") in resolver.connected(Identifier.get("a1"))

    assert resolver.get_judgement("a1", "a2") == Judgement.POSITIVE
    resolver.decide("b1", "b2", Judgement.POSITIVE)
    assert resolver.get_judgement("a1", "b1") == Judgement.NO_JUDGEMENT
    neg_canon = resolver.decide("a2", "b2", Judgement.NEGATIVE)
    assert neg_canon.id == "b2", neg_canon
    assert resolver.get_judgement("a2", "b2") == Judgement.NEGATIVE
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE
    resolver.suggest("a1", "b1", 7.0)
    assert resolver.get_judgement("a1", "b1") == Judgement.NEGATIVE

    resolver.decide("c1", "c2", Judgement.POSITIVE)
    assert len(list(resolver.canonicals())) == 3, list(resolver.canonicals())
    resolver.remove("c1")
    resolver.remove("c2")
    assert len(list(resolver.canonicals())) == 2, list(resolver.canonicals())

    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a2") == a_canon
    assert resolver.get_canonical("banana") == "banana"

    resolver.decide("a1", "a17", Judgement.POSITIVE)
    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a17") == a_canon
    resolver.decide("a1", "a0", Judgement.POSITIVE)
    assert resolver.get_canonical("a1") == a_canon
    assert resolver.get_canonical("a0") == a_canon
    assert len(list(resolver.canonicals())) == 2, list(resolver.canonicals())

    resolver.decide("a1", "a42", Judgement.POSITIVE)
    assert resolver.get_canonical("a42") == a_canon
    resolver.remove("a42")
    assert resolver.get_canonical("a42") == "a42"

    resolver._remove_edge
    resolver.suggest("c1", "c2", 7.0)
    assert (c1c2 := resolver.get_edge("c1", "c2")) and c1c2.score == 7.0
    resolver.suggest("c1", "c2", 8.0)
    edges = resolver.get_edges()
    # subsequent suggest() updates score
    assert (c1c2 := resolver.get_edge("c1", "c2")) and c1c2.score == 8.0
    assert c1c2 in edges, edges
    ccn = resolver.decide("c1", "c2", Judgement.POSITIVE)
    assert resolver.get_edge("c1", "c2") is None
    assert (ccnc2 := resolver.get_edge(ccn, "c2")) and ccnc2.score is None
    # positive decide() replaces non-canon edge with two towards canonical
    edges2 = resolver.get_edges()
    assert ccnc2 in edges2, edges2
    assert c1c2 not in edges2, edges2
    assert len(edges2) == len(edges) + 1, (edges, edges2)

    assert "a1" in resolver.get_referents(a_canon)
    assert "a1" in resolver.get_referents(a_canon, canonicals=False)
    # assert a_canon.id in resolver.get_referents(a_canon)
    assert a_canon.id not in resolver.get_referents(a_canon, canonicals=False)
    if settings.DB_URL.startswith("sqlite"):
        assert "sqlite:///:memory:" in repr(resolver)
    elif settings.DB_URL.startswith("postgres"):
        assert "postgresql://" in repr(resolver)
    else:
        assert False, "Expected DB_URL to start with 'sqlite://' or 'postgres://'"

    resolver.explode("a1")
    assert resolver.get_canonical("a17") == "a17"
    assert resolver.get_judgement(a_canon, "a1") == Judgement.NO_JUDGEMENT
    assert resolver.get_judgement("b1", "b2") == Judgement.POSITIVE

    # Can we actually commit after all these operations?
    resolver.commit()


def test_cluster_to_cluster(resolver):
    resolver.begin()
    a_canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    b_canon = resolver.decide("b1", "b2", Judgement.POSITIVE)
    resolver.decide(a_canon, b_canon, Judgement.UNSURE)
    resolver.decide(a_canon, "a3", Judgement.POSITIVE)
    resolver.remove("a3")

    assert "a1" in resolver.connected(Identifier.get("a1"))
    assert "a2" in resolver.connected(Identifier.get("a1"))
    assert "b1" not in resolver.connected(Identifier.get("a1"))
    assert Edge(a_canon, b_canon) in set(resolver._get_resolved_edges("a1", "b1"))

    # ab_canon = resolver.decide("a1", "b1", Judgement.POSITIVE)
    # TODO: There's a bug here - decide(a, b, POSITIVE) must always return a canonical.
    # assert ab_canon.canonical, ab_canon
    acbc_canon = resolver.decide(a_canon, b_canon, Judgement.POSITIVE)
    assert acbc_canon.canonical, acbc_canon
    # The pair the decision was made upon. get_resolved doesn't handle this case
    # because get_canonical should be called on the arguments first and
    # there's no edge between the same node.
    #         note:         NOT
    assert Edge("a1", "a2") not in set(resolver._get_resolved_edges("a1", "a2"))
    assert resolver.get_edge("a1", "a2") is None
    # A referent and canonical
    assert Edge("a1", a_canon) in set(resolver._get_resolved_edges("a1", a_canon))
    assert resolver.get_edge("a1", a_canon) == Edge("a1", a_canon)
    # Two referents whose canonicals were decided upon
    assert Edge(a_canon, b_canon) in set(resolver._get_resolved_edges("a1", "b1"))
    assert resolver.get_edge("a1", "b1") is None

    # indirect canonical
    a_ultimate = resolver.get_canonical("a1")
    b_ultimate = resolver.get_canonical("b1")
    assert a_ultimate == b_ultimate
    assert set(resolver.canonicals()) == {a_ultimate}
    assert len(list(resolver.canonicals())) == 1

    # indirect connected
    expected = {
        Identifier.get("a1"),
        Identifier.get("a2"),
        Identifier.get("b1"),
        Identifier.get(a_canon),
        Identifier.get(b_canon),
    }
    connected = resolver.connected(Identifier.get("a1"))
    assert expected.issubset(connected), (expected, connected)
    assert "a3" not in connected

    # Can we actually commit after all these operations?
    resolver.commit()


def test_linker(resolver):
    resolver.begin()
    canon_a = resolver.decide("a1", "a2", Judgement.POSITIVE)
    canon_a = resolver.decide(canon_a, "a3", Judgement.POSITIVE)
    resolver.remove("a3")
    canon_b = resolver.decide("b1", "b2", Judgement.POSITIVE)
    resolver.decide("a1", "Q123", Judgement.POSITIVE)
    resolver.decide("a2", "c2", Judgement.NEGATIVE)
    linker = resolver.get_linker()
    resolver.commit()

    assert len(linker.connected(canon_a)) == 4
    assert len(linker.connected(canon_b)) == 3

    assert len(linker._entities) == 7, linker._entities
    assert "a1" in linker.get_referents("Q123")
    assert "a2" in linker.get_referents("Q123")
    assert canon_a.id in linker.get_referents("Q123")
    assert "Q123" not in linker.get_referents("Q123")
    assert linker.get_canonical("a1") == "Q123"
    assert linker.get_canonical("b1") == canon_b
    assert linker.get_canonical("c2") == "c2"
    assert linker.get_canonical("x1") == "x1"
    assert linker.get_canonical("a3") == "a3"


def test_cached_linker(resolver):
    resolver = Resolver.make_default()
    resolver.begin()
    canon_a = resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert resolver.get_canonical("a1") == canon_a

    assert resolver._linker is None
    resolver.warm_linker()
    assert resolver._linker is not None
    # We get the same result as pre-warm
    assert resolver.get_canonical("a1") == canon_a

    canon_b = resolver.decide("b1", "b2", Judgement.POSITIVE)
    assert resolver._linker is None  # cache is cleared
    assert resolver.get_canonical("a1") == canon_a
    # New decision is available
    assert resolver.get_canonical("b1") == canon_b


def test_resolver_store_load(resolver, other_table_resolver):
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        resolver.begin()
        canon_a = resolver.decide("a1", "a2", Judgement.POSITIVE)
        resolver.decide(canon_a, "a3", Judgement.POSITIVE)
        resolver.remove("a3")
        resolver.decide("a2", "b2", Judgement.NEGATIVE)
        resolver.suggest("a1", "c1", 7.0)
        resolver.save(path)

        with open(path, "r") as fh:
            assert len(fh.readlines()) == 4

        get_engine.cache_clear()
        get_metadata.cache_clear()
        other_table_resolver.begin()
        other_table_resolver.load(path)
        assert len(other_table_resolver.get_edges()) == len(resolver.get_edges())
        edge = other_table_resolver.get_edge("a1", "c1")
        assert edge is not None, edge
        assert edge.score == 7.0
        assert other_table_resolver.get_canonical("a1") == canon_a


def test_resolver_candidates(resolver):
    resolver.begin()
    candidates = list(resolver.get_candidates())
    assert len(candidates) == 0, candidates

    resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide("a2", "b2", Judgement.NEGATIVE)
    resolver.suggest("a1", "b2", 7.0)
    resolver.suggest("a1", "c1", 5.0)
    resolver.suggest("a1", "d1", 4.0)

    candidates = list(resolver.get_candidates())
    assert len(candidates) == 2, candidates
    assert candidates[0][2] == 5.0, candidates

    resolver.prune()
    candidates = list(resolver.get_candidates())
    assert len(candidates) == 0, candidates
    resolver.commit()


def test_get_judgments(resolver):
    resolver.begin()
    canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide(canon, "a3", Judgement.POSITIVE)
    resolver.decide(canon, "a4", Judgement.POSITIVE)
    resolver.decide(canon, "b1", Judgement.NEGATIVE)
    resolver.decide(canon, "b2", Judgement.NEGATIVE)
    resolver.decide(canon, "a3", Judgement.UNSURE)
    resolver.remove("b2")
    edges = resolver.get_judgements(limit=3)
    jgmts = [(e.source.id, e.judgement) for e in edges]
    assert jgmts == [
        ("a3", Judgement.UNSURE),  # first, because it's the last edit
        # b2 was "soft deleted"
        ("b1", Judgement.NEGATIVE),
        ("a4", Judgement.POSITIVE),
        # a1 and a2 to canon excluded by limit.
    ]


def test_resolver_statements(resolver, other_table_resolver):
    resolver.begin()
    canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide("a2", "b2", Judgement.NEGATIVE)

    stmt = Statement("a1", "holder", "Passport", "b2", "test")

    # A resolver canonicalises the statement entity ID but not ID values.
    stmt = resolver.apply_statement(stmt)
    assert stmt.canonical_id == canon.id
    assert stmt.value == "b2"

    # A resolver that doesn't know about the entity doesn't alter stmt.
    other_table_resolver.begin()
    stmt = other_table_resolver.apply_statement(stmt)
    assert stmt.canonical_id == "a1"
    assert stmt.value == "b2"


def test_table_name(resolver, other_table_resolver):
    """Make fairly sure that we're hitting the correct table"""
    resolver.begin()
    resolver.decide("b1", "b2", Judgement.POSITIVE)  # No a1
    resolver.decide("c1", "c2", Judgement.POSITIVE)  # 4 edges
    resolver.commit()

    other_table_resolver.begin()
    a_canon = other_table_resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert other_table_resolver.get_judgement("a1", "a2") == Judgement.POSITIVE
    assert other_table_resolver.get_canonical("a1") == a_canon
    assert set(other_table_resolver.canonicals()) == {a_canon}
    assert other_table_resolver.get_edge("a1", a_canon) is not None
    assert len(other_table_resolver.get_edges()) == 2
    assert "another_table" in repr(other_table_resolver)
