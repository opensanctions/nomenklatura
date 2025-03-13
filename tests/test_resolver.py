from pathlib import Path
from tempfile import NamedTemporaryFile

from nomenklatura import settings
from nomenklatura.db import get_engine
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Identifier
from nomenklatura.resolver.edge import Edge
from nomenklatura.resolver.resolver import Resolver
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
    assert set(n.id for n in resolver.nodes) == {"a1", "a2", a_canon.id}

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

    resolver.suggest("c1", "c2", 7.0)
    assert (c1c2 := resolver.get_edge("c1", "c2")) and c1c2.score == 7.0
    resolver.suggest("c1", "c2", 8.0)
    edge_count = len(resolver.edges)
    # subsequent suggest() updates score
    assert (c1c2 := resolver.get_edge("c1", "c2")) and c1c2.score == 8.0
    assert c1c2 in resolver.edges, resolver.edges
    ccn = resolver.decide("c1", "c2", Judgement.POSITIVE)
    assert resolver.get_edge("c1", "c2") is None
    assert (ccnc2 := resolver.get_edge(ccn, "c2")) and ccnc2.score is None
    # positive decide() replaces non-canon edge with two towards canonical

    assert ccnc2.key in resolver.edges, resolver.edges
    assert c1c2.key not in resolver.edges, resolver.edges
    assert len(resolver.edges) == edge_count + 1

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
    assert Edge(a_canon, b_canon) == resolver.get_resolved_edge("a1", "b1")

    # ab_canon = resolver.decide("a1", "b1", Judgement.POSITIVE)
    # TODO: There's a bug here - decide(a, b, POSITIVE) must always return a canonical.
    # assert ab_canon.canonical, ab_canon
    acbc_canon = resolver.decide(a_canon, b_canon, Judgement.POSITIVE)
    assert acbc_canon.canonical, acbc_canon
    assert resolver.get_resolved_edge("a1", "a2") is not None
    assert resolver.get_edge("a1", "a2") is None
    # A referent and canonical
    assert resolver.get_resolved_edge("a1", a_canon) is not None
    assert resolver.get_edge("a1", a_canon) == Edge("a1", a_canon)
    # Two referents whose canonicals were decided upon
    assert resolver.get_resolved_edge("a1", "b1") is not None
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

    # clusters:
    #   Q123 canon_a a1 a2 # removed a3
    #   canon_b b1 b2
    #   c2
    assert len(linker._entities) == 8, linker._entities
    assert "a1" in linker.get_referents("Q123")
    assert "a2" in linker.get_referents("Q123")
    assert canon_a.id in linker.get_referents("Q123")
    assert "Q123" not in linker.get_referents("Q123")
    assert linker.get_canonical("a1") == "Q123"
    assert linker.get_canonical("b1") == canon_b
    assert linker.get_canonical("c2") == "c2"
    assert linker.get_canonical("x1") == "x1"
    assert linker.get_canonical("a3") == "a3"


def test_update_from_db(resolver):
    """
    This tests that one resolver instance can load updates from the db made by
    another instance.

    On SQLite this is not concurrent - it only tests the update loading.
    On Postgres this also tests transaction winners.
    """
    r1 = Resolver.make_default()
    # we don't get_engine.cache_clear() because we want the same db,
    # even when using in-memory sqlite.
    r2 = Resolver.make_default()

    try:
        r1.begin()
        r2.begin()
        assert set(r1.canonicals()) == set()
        r1.suggest("a1", "a2", 1.0, "test user")
        r2.suggest("b1", "b2", 1.0, "test user")
        r1.commit()
        r2.commit()

        r1.begin()
        r2.begin()
        canon_a = r1.decide("a1", "a2", Judgement.POSITIVE, user="r1")
        canon_b = r2.decide("b1", "b2", Judgement.POSITIVE, user="r2")
        assert set(r1.canonicals()) == {canon_a}
        assert set(r2.canonicals()) == {canon_b}
        r1.suggest(canon_a, "a3", 1.0, "test user")
        r1.commit()
        r2.commit()

        r1.begin()
        r2.begin()
        # They see each others' decisions
        assert set(r1.canonicals()) == {canon_a, canon_b}
        assert set(r2.canonicals()) == {canon_a, canon_b}
        # Validity for delete check
        assert Identifier.get("a2") in r1.connected(canon_a)
        assert Identifier.get("b2") in r2.connected(canon_b)
        r1.remove("b2")
        r2.remove("a2")
        # TODO: postgres locks when these are happening in concurrent transactions
        # r1.decide(canon_a, "a3", Judgement.POSITIVE, user="r1")
        # r2.decide(canon_a, "a3", Judgement.UNSURE, user="r2")
        r1.commit()
        r2.commit()

        r1.begin()
        r2.begin()
        # They see each others' deletes
        assert Identifier.get("a2") not in r1.connected(canon_a)
        assert Identifier.get("b2") not in r2.connected(canon_b)
        # TODO: what determines which one wins?
        # assert r1.get_judgement(canon_a, "a3") == Judgement.UNSURE
        # assert r2.get_judgement(canon_a, "a3") == Judgement.UNSURE
        r1.commit()
        r2.commit()

        # r1.begin()
        # from pprint import pprint
        # from sqlalchemy import text
        # pprint(r1._get_connection().execute(text("SELECT * FROM resolver")).fetchall())
        # assert False
    finally:
        r1.rollback(force=True)
        r2.rollback(force=True)
        r1._table.drop(r1._engine)


def test_resolver_store_load(resolver, other_table_resolver):
    with NamedTemporaryFile("w") as fh:
        path = Path(fh.name)
        resolver.begin()
        canon_a = resolver.decide("a1", "a2", Judgement.POSITIVE)
        resolver.decide(canon_a, "a3", Judgement.POSITIVE)
        resolver.remove("a3")
        resolver.decide("a2", "b2", Judgement.NEGATIVE)
        resolver.suggest("a1", "c1", 7.0)
        resolver.dump(path)

        with open(path, "r") as fh:
            assert len(fh.readlines()) == 4

        other_table_resolver.begin()
        other_table_resolver.load(path)
        assert len(other_table_resolver.edges) == len(resolver.edges)

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


def test_get_judgements(resolver):
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
    assert len(other_table_resolver.edges) == 2
    assert "another_table" in repr(other_table_resolver)
