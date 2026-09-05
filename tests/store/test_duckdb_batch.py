import os
import tempfile
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


def test_duckdb_batch_store_mapping_csv_roundtrip(test_dataset: Dataset) -> None:
    """The mapping travels through a CSV file; ids must survive quoting."""
    awkward = ["comma,id", 'quote"id', "line\nid", "NULL", " padded "]
    entities = [
        {"id": eid, "schema": "Person", "properties": {"name": [f"Name {i}"]}}
        for i, eid in enumerate(awkward)
    ]
    linker: Linker[Entity] = Linker({})
    canonical = linker.add(awkward[0], awkward[1])
    for eid in awkward[2:]:
        canonical = linker.add(canonical, eid)

    conn = duckdb.connect()
    _load_statements(conn, test_dataset, entities)
    tmp_before = set(os.listdir(tempfile.gettempdir()))
    store = DuckDBBatchStore(test_dataset, linker, conn, "statements")
    view = store.default_view()
    assert set(os.listdir(tempfile.gettempdir())) == tmp_before

    proxies = list(view.entities())
    assert len(proxies) == 1
    merged = proxies[0]
    assert merged.id == canonical
    assert set(merged.get("name")) == {f"Name {i}" for i in range(len(awkward))}
    assert view.get_entity(canonical) is not None


class _CountingConn:
    """Counts cursor handouts, i.e. lazy read queries on the view."""

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self.inner = conn
        self.cursors = 0

    def cursor(self) -> duckdb.DuckDBPyConnection:
        self.cursors += 1
        return self.inner.cursor()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def test_duckdb_batch_store_prefetch_parity(
    test_dataset: Dataset,
    donations_json: list[dict[str, Any]],
    resolver: Resolver[Entity],
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, donations_json)
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    lazy_view = store.default_view()
    pre_view = store.default_view()
    lazy = {e.id: e for e in lazy_view.entities()}

    count = 0
    for entity in pre_view.entities(prefetch_nested=True):
        count += 1
        expected = lazy[entity.id]
        assert entity.schema == expected.schema
        assert len(list(entity.statements)) == len(list(expected.statements))
        adjacent = sorted((p.name, a.id) for p, a in pre_view.get_adjacent(entity))
        assert adjacent == sorted(
            (p.name, a.id) for p, a in lazy_view.get_adjacent(expected)
        )
        assert entity.id is not None
        inverted = sorted((p.name, a.id) for p, a in pre_view.get_inverted(entity.id))
        assert inverted == sorted(
            (p.name, a.id) for p, a in lazy_view.get_inverted(entity.id)
        )
    assert count == len(lazy)
    # The rolling caches are dropped once the scan completes:
    assert pre_view._cache == {}
    assert pre_view._inverted == {}


def test_duckdb_batch_store_prefetch_queries(
    test_dataset: Dataset,
    donations_json: list[dict[str, Any]],
    resolver: Resolver[Entity],
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, donations_json)
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    view = store.default_view()
    counting = _CountingConn(conn)
    store.conn = counting  # type: ignore[assignment]

    # Mimic the nested export: traverse each root's adjacency and recurse
    # through edge-schema neighbors to their endpoints.
    traversed = 0
    for entity in view.entities(prefetch_nested=True):
        for _, adjacent in view.get_adjacent(entity):
            traversed += 1
            if adjacent.schema.edge:
                for _, _ in view.get_adjacent(adjacent):
                    traversed += 1
    assert traversed > 100
    # One scan plus the prefetch round for the single batch; no per-entity
    # lazy queries during traversal.
    assert counting.cursors <= 5


def test_duckdb_batch_store_prefetch_hub_guard(
    monkeypatch: pytest.MonkeyPatch,
    test_dataset: Dataset,
    donations_json: list[dict[str, Any]],
    resolver: Resolver[Entity],
) -> None:
    # With a zero cap, every id with owners is a "hub": it must stay out of
    # the inverted cache and fall back to the complete lazy path.
    monkeypatch.setattr("nomenklatura.store.duckdb_batch.INVERTED_CAP", 0)
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, donations_json)
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    lazy_view = store.default_view()
    pre_view = store.default_view()

    hubs = 0
    for entity in pre_view.entities(prefetch_nested=True):
        assert entity.id is not None
        inverted = sorted((p.name, a.id) for p, a in pre_view.get_inverted(entity.id))
        assert inverted == sorted(
            (p.name, a.id) for p, a in lazy_view.get_inverted(entity.id)
        )
        if len(inverted) > 0:
            assert entity.id not in pre_view._inverted
            hubs += 1
        else:
            assert pre_view._inverted.get(entity.id) == []
    assert hubs > 0


def test_duckdb_batch_store_prefetch_update_invalidates(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> None:
    conn = duckdb.connect()
    _load_statements(conn, test_dataset, [PERSON, PERSON_EXT])
    store = DuckDBBatchStore(test_dataset, resolver, conn, "statements")
    view = store.default_view()

    scan = view.entities(prefetch_nested=True)
    assert next(scan) is not None
    assert len(view._cache) > 0

    merged_id = resolver.decide(
        "john-doe", "john-doe-2", judgement=Judgement.POSITIVE, user="test"
    )
    store.update(merged_id.id)
    assert view._cache == {}
    assert view._inverted == {}
    assert view.get_entity(merged_id.id) is not None
    assert view.get_entity("john-doe") is None


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
