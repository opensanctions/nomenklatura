from typing import Any

import duckdb
import pytest
from followthemoney import Dataset, model
from followthemoney import StatementEntity as Entity

from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Linker, Resolver
from nomenklatura.store.duckdb_ import DuckDBStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
TCHIBO = "4e0bd810e1fcb49990a2b31709b6140c4c9139c5"

PERSON = {
    "id": "john-doe",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}

PERSON_EXT = {
    "id": "john-doe-2",
    "schema": "Person",
    "properties": {"birthPlace": ["North Texas"]},
}

CREATE_SQL = """
    CREATE TABLE statements (
        id VARCHAR, entity_id VARCHAR, "schema" VARCHAR, prop VARCHAR,
        value VARCHAR, dataset VARCHAR, lang VARCHAR, original_value VARCHAR,
        origin VARCHAR, external BOOLEAN, first_seen TIMESTAMP, last_seen TIMESTAMP
    )
"""


def _load_statements(
    conn: duckdb.DuckDBPyConnection, dataset: Dataset, entities: list[dict[str, Any]]
) -> None:
    conn.execute(CREATE_SQL)
    rows = []
    for data in entities:
        proxy = Entity.from_data(dataset, data)
        for stmt in proxy.statements:
            if stmt.entity_id is None:
                continue
            rows.append(
                (
                    stmt.id or stmt.generate_key(),
                    stmt.entity_id,
                    stmt.schema,
                    stmt.prop,
                    stmt.value,
                    stmt.dataset,
                    stmt.lang,
                    stmt.original_value,
                    stmt.origin,
                    stmt.external,
                    stmt.first_seen,
                    stmt.last_seen,
                )
            )
    conn.executemany(
        "INSERT INTO statements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )


@pytest.mark.parametrize("materialize", [False, True])
def test_duckdb_store_donations(
    test_dataset: Dataset,
    donations_json: list[dict[str, Any]],
    resolver: Resolver[Entity],
    materialize: bool,
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, donations_json)
    store = DuckDBStore(
        test_dataset, resolver, conn, "statements", materialize=materialize
    )
    view = store.default_view()

    proxies = list(view.entities())
    assert len(proxies) == len(donations_json)

    address = model.get("Address")
    assert address is not None
    addresses = list(view.entities(include_schemata=[address]))
    assert len(addresses) == 89
    assert all(e.schema == address for e in addresses)

    assert not view.has_entity("banana")
    assert view.get_entity("banana") is None
    assert view.has_entity(TCHIBO)
    entity = view.get_entity(TCHIBO)
    assert entity is not None
    assert entity.caption == "Tchibo Holding AG"

    bulk = list(view.get_entities([TCHIBO, DAIMLER]))
    assert len(bulk) == 2
    assert {e.id for e in bulk} == {TCHIBO, DAIMLER}

    tested = False
    for prop, value in entity.itervalues():
        if prop.type.name == "entity":
            for iprop, ientity in view.get_inverted(value):
                assert iprop.reverse == prop
                assert ientity == entity
                tested = True
    assert tested

    adjacent = list(view.get_adjacent(entity))
    assert len(adjacent) == 2

    with pytest.raises(NotImplementedError):
        store.writer()
    # update() is a read-time-canonicalization no-op:
    store.update(TCHIBO)


@pytest.mark.parametrize("materialize", [False, True])
def test_duckdb_store_merge(
    test_dataset: Dataset, resolver: Resolver[Entity], materialize: bool
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON, PERSON_EXT])
    store = DuckDBStore(
        test_dataset, resolver, conn, "statements", materialize=materialize
    )
    assert len(list(store.default_view().entities())) == 2

    merged_id = resolver.decide(
        "john-doe", "john-doe-2", judgement=Judgement.POSITIVE, user="test"
    )
    # No store.update() rewrite needed: a fresh store over the same relation
    # picks the merge up purely from the linker.
    store = DuckDBStore(
        test_dataset, resolver, conn, "statements", materialize=materialize
    )
    view = store.default_view()
    proxies = list(view.entities())
    assert len(proxies) == 1
    merged = proxies[0]
    assert merged.id == merged_id
    assert "John Doe" in merged.get("name")
    assert "North Texas" in merged.get("birthPlace")
    assert "john-doe" in merged.referents

    # Point reads resolve any cluster member to the merged entity:
    by_member = view.get_entity("john-doe")
    assert by_member is not None
    assert by_member.id == merged_id


def test_duckdb_store_relation_validation(test_dataset: Dataset) -> None:
    linker: Linker[Entity] = Linker({})
    conn = duckdb.connect()
    with pytest.raises(ValueError):
        DuckDBStore(test_dataset, linker, conn, "nope; DROP TABLE x")
    with pytest.raises(duckdb.Error):
        DuckDBStore(test_dataset, linker, conn, "missing_relation")


def test_linker_iter_pairs() -> None:
    cluster = ("NK-canon", "src-b", "src-a")
    mapping = {node: cluster for node in cluster}
    linker: Linker[Entity] = Linker(mapping)
    pairs = set(linker.iter_pairs())
    assert pairs == {("src-a", "NK-canon"), ("src-b", "NK-canon")}
    empty: Linker[Entity] = Linker({})
    assert list(empty.iter_pairs()) == []


def test_resolver_iter_pairs(resolver: Resolver[Entity]) -> None:
    merged_id = resolver.decide(
        "src-1", "src-2", judgement=Judgement.POSITIVE, user="test"
    )
    pairs = set(resolver.iter_pairs())
    assert ("src-1", merged_id) in pairs
    assert ("src-2", merged_id) in pairs
