from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import MetaData

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


def test_resolver():
    resolver = Resolver.make_default()
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
    assert ":memory:" in repr(resolver)

    resolver.explode("a1")
    assert resolver.get_canonical("a17") == "a17"
    assert resolver.get_judgement(a_canon, "a1") == Judgement.NO_JUDGEMENT
    assert resolver.get_judgement("b1", "b2") == Judgement.POSITIVE

    # Can we actually commit after all these operations?
    resolver.commit()


def test_cluster_to_cluster():
    resolver = Resolver.make_default()
    resolver.begin()

    a_canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    b_canon = resolver.decide("b1", "b2", Judgement.POSITIVE)
    _acbc = resolver.decide(a_canon, b_canon, Judgement.UNSURE)
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

    resolver.commit()


def test_linker():
    resolver = Resolver.make_default()
    resolver.begin()
    canon_a = resolver.decide("a1", "a2", Judgement.POSITIVE)
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


def test_cached_linker():
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


def test_resolver_store():
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        resolver = Resolver.make_default()
        resolver.begin()
        resolver.decide("a1", "a2", Judgement.POSITIVE)
        resolver.decide("a2", "b2", Judgement.NEGATIVE)
        resolver.suggest("a1", "c1", 7.0)
        resolver.save(path)

        get_engine.cache_clear()
        get_metadata.cache_clear()
        other = Resolver(engine=get_engine(), metadata=get_metadata(), create=True)
        other.begin()
        other.load(path)
        assert len(other.get_edges()) == len(resolver.get_edges())
        edge = other.get_edge("a1", "c1")
        assert edge is not None, edge
        assert edge.score == 7.0
        other.commit()


def test_resolver_candidates():
    resolver = Resolver.make_default()
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


def test_resolver_statements():
    resolver = Resolver.make_default()
    resolver.begin()
    canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    resolver.decide("a2", "b2", Judgement.NEGATIVE)

    stmt = Statement("a1", "holder", "Passport", "b2", "test")
    stmt = resolver.apply_statement(stmt)
    assert stmt.canonical_id == str(canon)
    assert stmt.value == "b2"
    resolver.commit()

    get_engine.cache_clear()
    get_metadata.cache_clear()
    other = Resolver(engine=get_engine(), metadata=get_metadata(), create=True)
    other.begin()
    stmt = other.apply_statement(stmt)
    assert stmt.canonical_id == "a1"
    assert stmt.value == "b2"
    other.commit()


def test_table_name():
    """Make fairly sure that we're hitting the correct table"""
    default_resolver = Resolver.make_default()
    default_resolver.begin()
    default_resolver.decide("b1", "b2", Judgement.POSITIVE)  # No a1
    default_resolver.decide("c1", "c2", Judgement.POSITIVE)  # 4 edges
    default_resolver.commit()

    engine = get_engine()
    meta = MetaData()
    resolver = Resolver(engine, meta, create=True, table_name="another_table")
    resolver.begin()
    a_canon = resolver.decide("a1", "a2", Judgement.POSITIVE)
    assert resolver.get_judgement("a1", "a2") == Judgement.POSITIVE
    assert resolver.get_canonical("a1") == a_canon
    assert set(resolver.canonicals()) == {a_canon}
    assert resolver.get_edge("a1", a_canon) is not None
    assert len(resolver.get_edges()) == 2
    assert "another_table" in repr(resolver)
    resolver.rollback()
