from typing import Any

import duckdb
import pytest
from followthemoney import Dataset, model
from followthemoney import StatementEntity as Entity

from nomenklatura import duck
from nomenklatura.judgement import Judgement
from nomenklatura.resolver import Linker, Resolver
from nomenklatura.store.duckdb_batch import DuckDBBatchStore

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

STATEMENT_DDL = ", ".join(
    f'"{name}" {type_}' for name, type_ in duck.STATEMENT_COLUMNS.items()
)


def _load_statements(
    conn: duckdb.DuckDBPyConnection,
    dataset: Dataset,
    entities: list[dict[str, Any]],
    external: bool = False,
) -> None:
    conn.execute(f"CREATE TABLE IF NOT EXISTS statements ({STATEMENT_DDL})")
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
                    external,
                    stmt.first_seen,
                    stmt.last_seen,
                )
            )
    conn.executemany(
        "INSERT INTO statements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows
    )


def test_duckdb_batch_store_donations(
    test_dataset: Dataset,
    donations_json: list[dict[str, Any]],
    resolver: Resolver[Entity],
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, donations_json)
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
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


def test_duckdb_batch_store_update(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON, PERSON_EXT])
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    view = store.default_view()
    assert len(list(view.entities())) == 2

    merged_id = resolver.decide(
        "john-doe", "john-doe-2", judgement=Judgement.POSITIVE, user="test"
    )
    store.update(merged_id.id)

    # The merge is visible in the existing view, no rebuild needed:
    proxies = list(view.entities())
    assert len(proxies) == 1
    merged = proxies[0]
    assert merged.id == merged_id
    assert "John Doe" in merged.get("name")
    assert "North Texas" in merged.get("birthPlace")
    assert "john-doe" in merged.referents

    # Point reads take canonical ids, as in the other store backends; member
    # ids are the caller's job to resolve through the linker:
    assert view.get_entity(merged_id.id) is not None
    assert view.get_entity("john-doe") is None
    assert not view.has_entity("john-doe")


def test_duckdb_batch_store_include_schemata(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    legal_entity = model.get("LegalEntity")
    company = model.get("Company")
    assert legal_entity is not None and company is not None
    conn = duckdb.connect()
    _load_statements(
        conn,
        test_dataset,
        [
            {"id": "acme", "schema": "LegalEntity", "properties": {"name": ["ACME"]}},
            {"id": "acme-2", "schema": "Company", "properties": {"name": ["ACME Inc"]}},
        ],
    )
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    view = store.default_view()
    merged_id = resolver.decide(
        "acme", "acme-2", judgement=Judgement.POSITIVE, user="test"
    )
    store.update(merged_id.id)

    # The merged cluster assembles to Company (the narrower schema), so the
    # exact-match filter must exclude it for LegalEntity despite the cluster
    # containing LegalEntity statements:
    assert list(view.entities(include_schemata=[legal_entity])) == []
    companies = list(view.entities(include_schemata=[company]))
    assert [e.id for e in companies] == [merged_id.id]
    assert list(view.entities(include_schemata=[])) == []


def test_duckdb_batch_store_multi_view_update(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON, PERSON_EXT])
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    first = store.default_view()
    second = store.default_view()

    merged_id = resolver.decide(
        "john-doe", "john-doe-2", judgement=Judgement.POSITIVE, user="test"
    )
    store.update(merged_id.id)
    for view in (first, second):
        assert len(list(view.entities())) == 1
        entity = view.get_entity(merged_id.id)
        assert entity is not None
        assert entity.id == merged_id


def test_duckdb_batch_store_external(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON])
    _load_statements(conn, test_dataset, [PERSON_EXT], external=True)
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")

    internal = store.view(test_dataset, external=False)
    assert {e.id for e in internal.entities()} == {"john-doe"}
    assert not internal.has_entity("john-doe-2")

    external = store.view(test_dataset, external=True)
    assert {e.id for e in external.entities()} == {"john-doe", "john-doe-2"}


def test_duckdb_batch_store_close(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON])
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    store.default_view()

    def nk_tables() -> set[str]:
        rows = conn.execute(
            "SELECT table_name FROM duckdb_tables() WHERE table_name LIKE 'nk_%'"
        ).fetchall()
        return {row[0] for row in rows}

    assert len(nk_tables()) == 2  # statements + edges; mapping already dropped
    store.close()
    assert len(nk_tables()) == 0
    # The caller's connection and relation survive:
    assert conn.execute("SELECT count(*) FROM statements").fetchone() is not None


def test_duckdb_batch_store_validation(test_dataset: Dataset) -> None:
    linker: Linker[Entity] = Linker({})
    conn = duckdb.connect()
    with pytest.raises(ValueError, match="Invalid relation name"):
        DuckDBBatchStore(test_dataset, linker, conn, "nope; DROP TABLE x")
    with pytest.raises(duckdb.Error):
        DuckDBBatchStore(test_dataset, linker, conn, "missing_relation")
    conn.execute("CREATE TABLE mistyped (id VARCHAR, entity_id VARCHAR)")
    with pytest.raises(ValueError, match="not a valid statement relation"):
        DuckDBBatchStore(test_dataset, linker, conn, "mistyped")
