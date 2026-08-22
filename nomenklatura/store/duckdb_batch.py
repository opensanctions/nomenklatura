#
# Materialized, read-heavy statement store on top of a DuckDB relation.
#
from collections.abc import Generator, Iterable
from itertools import count
from typing import Any

import duckdb
from followthemoney import DS, SE, Property, Schema, Statement, model, registry

from nomenklatura import duck
from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer

FETCH_SIZE = 10_000
INSERT_BATCH = 50_000

RAW_COLUMNS = (
    's.id, s.entity_id, s."schema", s.prop, s.value, s.dataset, s.lang, '
    "s.original_value, s.origin, s.external, s.first_seen, s.last_seen"
)
STMT_COLUMNS = (
    's.id, s.entity_id, s."schema", s.prop, s.value, s.dataset, s.lang, '
    "s.original_value, s.origin, s.external, "
    "strftime(s.first_seen, '%Y-%m-%dT%H:%M:%S') AS first_seen, "
    "strftime(s.last_seen, '%Y-%m-%dT%H:%M:%S') AS last_seen"
)

# Distinguishes the tables of every view created in this process, so stores
# sharing one connection cannot clobber each other's materializations.
_VIEW_SEQ = count()


def _statement(row: tuple[Any, ...], canonical_id: str) -> Statement:
    (
        sid,
        entity_id,
        schema,
        prop,
        value,
        dataset,
        lang,
        original_value,
        origin,
        external,
        first_seen,
        last_seen,
    ) = row
    return Statement(
        id=sid,
        entity_id=entity_id,
        prop=prop,
        schema=schema,
        value=value,
        dataset=dataset,
        lang=lang,
        original_value=original_value,
        origin=origin,
        external=external,
        first_seen=first_seen,
        last_seen=last_seen,
        canonical_id=canonical_id,
    )


def _entity_prop_values() -> str:
    """Render the entity-typed (schema, prop) pairs as an inline VALUES list."""
    pairs: set[tuple[str, str]] = set()
    for schema in model.schemata.values():
        for prop in schema.properties.values():
            if prop.type == registry.entity and not prop.stub:
                pairs.add((schema.name, prop.name))
    return ", ".join(f"('{s}', '{p}')" for s, p in sorted(pairs))


class DuckDBBatchStore(Store[DS, SE]):
    """Serve entities out of a statement relation, materialized per view.

    Use this to run batch consumers (xref, exports, enrichment) off immutable
    statement artifacts (e.g. parquet files, see `duck.STATEMENT_COLUMNS`)
    instead of first syncing a mutable store. Creating a view bakes the
    linker's resolution, the view's scope and its external flag into a table
    sorted and indexed on canonical_id — pay seconds per few million
    statements once, then the read loop pays index probes, not join work.
    Dedupe decisions made after the build become visible via `update()`,
    which re-keys the affected cluster in every view."""

    def __init__(
        self,
        dataset: DS,
        linker: Linker[SE],
        conn: duckdb.DuckDBPyConnection,
        relation: str,
    ) -> None:
        super().__init__(dataset, linker)
        duck.validate_statement_relation(conn, relation)
        self.conn = conn
        self.relation = relation
        self._views: list[DuckDBBatchView[DS, SE]] = []

    def writer(self) -> Writer[DS, SE]:
        raise NotImplementedError("DuckDBBatchStore is read-only")

    def update(self, id: str) -> None:
        canonical = self.linker.get_canonical(id)
        ids = set(self.linker.get_referents(canonical, canonicals=True))
        ids.add(canonical)
        for view in self._views:
            view._update(canonical, ids)

    def view(self, scope: DS, external: bool = False) -> View[DS, SE]:
        view = DuckDBBatchView(self, scope, external=external)
        self._views.append(view)
        return view

    def close(self) -> None:
        # Drop run-scoped state; the connection is owned by the caller.
        for view in self._views:
            view._drop()


class DuckDBBatchView(View[DS, SE]):
    def __init__(
        self, store: DuckDBBatchStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: DuckDBBatchStore[DS, SE] = store
        seq = next(_VIEW_SEQ)
        self.stmt_table = f"nk_stmts_{seq}"
        self.edge_table = f"nk_edges_{seq}"
        self._build(f"nk_mapping_{seq}")

    def _build(self, mapping: str) -> None:
        """Bake scope, external flag and current resolution into tables.

        The statement table clusters row groups by canonical_id and carries an
        ART index on top, so both full scans and point reads come cheap. The
        edge table pre-resolves entity-typed property values on both sides,
        making inverted lookups single probes instead of per-read referent
        expansion. The linker mapping is loaded only to serve these two joins
        and dropped again; afterwards all canonicalisation goes through the
        linker in Python."""
        conn = self.store.conn
        conn.execute(
            f"CREATE OR REPLACE TABLE {mapping} "
            "(entity_id VARCHAR, canonical_id VARCHAR)"
        )
        batch: list[tuple[str, str]] = []
        for pair in self.store.linker.mappings():
            batch.append(pair)
            if len(batch) >= INSERT_BATCH:
                conn.executemany(f"INSERT INTO {mapping} VALUES (?, ?)", batch)
                batch.clear()
        if len(batch) > 0:
            conn.executemany(f"INSERT INTO {mapping} VALUES (?, ?)", batch)

        names = sorted(self.dataset_names)
        holes = ", ".join("?" for _ in names)
        where = f"s.dataset IN ({holes})"
        if self.external is False:
            where += " AND NOT s.external"
        conn.execute(
            f"CREATE OR REPLACE TABLE {self.stmt_table} AS "
            f"SELECT {RAW_COLUMNS}, "
            f"coalesce(m.canonical_id, s.entity_id) AS canonical_id "
            f"FROM {self.store.relation} s "
            f"LEFT JOIN {mapping} m ON m.entity_id = s.entity_id "
            f"WHERE {where} ORDER BY canonical_id",
            names,
        )
        conn.execute(
            f"CREATE INDEX {self.stmt_table}_canonical "
            f"ON {self.stmt_table} (canonical_id)"
        )
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {self.edge_table} AS
            SELECT
                s.value AS value_entity_id,
                coalesce(mv.canonical_id, s.value) AS value_canonical_id,
                s.entity_id AS origin_entity_id,
                s.canonical_id AS origin_canonical_id
            FROM {self.stmt_table} s
            JOIN (VALUES {_entity_prop_values()}) p("schema", prop)
                ON p."schema" = s."schema" AND p.prop = s.prop
            LEFT JOIN {mapping} mv ON mv.entity_id = s.value
            """
        )
        conn.execute(f"DROP TABLE {mapping}")

    def _update(self, canonical: str, ids: set[str]) -> None:
        """Re-key a cluster's rows to its current canonical identifier."""
        holes = ", ".join("?" for _ in ids)
        params = [canonical, *ids]
        conn = self.store.conn
        conn.execute(
            f"UPDATE {self.stmt_table} SET canonical_id = ? "
            f"WHERE entity_id IN ({holes})",
            params,
        )
        conn.execute(
            f"UPDATE {self.edge_table} SET origin_canonical_id = ? "
            f"WHERE origin_entity_id IN ({holes})",
            params,
        )
        conn.execute(
            f"UPDATE {self.edge_table} SET value_canonical_id = ? "
            f"WHERE value_entity_id IN ({holes})",
            params,
        )

    def _drop(self) -> None:
        self.store.conn.execute(f"DROP TABLE IF EXISTS {self.stmt_table}")
        self.store.conn.execute(f"DROP TABLE IF EXISTS {self.edge_table}")

    def has_entity(self, id: str) -> bool:
        cursor = self.store.conn.cursor()
        try:
            row = cursor.execute(
                f"SELECT 1 FROM {self.stmt_table} WHERE canonical_id = ? LIMIT 1",
                [id],
            ).fetchone()
            return row is not None
        finally:
            cursor.close()

    def get_entity(self, id: str) -> SE | None:
        for entity in self.get_entities([id]):
            return entity
        return None

    def get_entities(self, ids: Iterable[str]) -> Generator[SE, None, None]:
        """Fetch a batch of entities in a single query."""
        lookup = set(ids)
        if len(lookup) == 0:
            return
        holes = ", ".join("?" for _ in lookup)
        clusters: dict[str, list[Statement]] = {}
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(
                f"SELECT {STMT_COLUMNS}, s.canonical_id FROM {self.stmt_table} s "
                f"WHERE s.canonical_id IN ({holes})",
                list(lookup),
            )
            while rows := result.fetchmany(FETCH_SIZE):
                for row in rows:
                    canonical_id = row[-1]
                    stmt = _statement(row[:-1], canonical_id)
                    clusters.setdefault(canonical_id, []).append(stmt)
        finally:
            cursor.close()
        for statements in clusters.values():
            entity = self.store.assemble(statements)
            if entity is not None:
                yield entity

    def get_inverted(self, id: str) -> Generator[tuple[Property, SE], None, None]:
        owners: set[str] = set()
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(
                f"SELECT DISTINCT e.origin_canonical_id FROM {self.edge_table} e "
                f"WHERE e.value_canonical_id = ?",
                [id],
            )
            while rows := result.fetchmany(FETCH_SIZE):
                owners.update(row[0] for row in rows)
        finally:
            cursor.close()
        for entity in self.get_entities(owners):
            for prop, value in entity.itervalues():
                if value == id and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(
        self, include_schemata: list[Schema] | None = None
    ) -> Generator[SE, None, None]:
        query = f"SELECT {STMT_COLUMNS}, s.canonical_id FROM {self.stmt_table} s "
        params: list[str] = []
        if include_schemata is not None:
            # Prefilter clusters in SQL: an assembled entity's schema is always
            # one of its statements' schema values.
            params = sorted(schema.name for schema in include_schemata)
            if len(params) == 0:
                return
            holes = ", ".join("?" for _ in params)
            query += (
                f"WHERE s.canonical_id IN (SELECT canonical_id "
                f'FROM {self.stmt_table} WHERE "schema" IN ({holes})) '
            )
        query += "ORDER BY s.canonical_id"
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(query, params)
            statements: list[Statement] = []
            previous: str | None = None
            while rows := result.fetchmany(FETCH_SIZE):
                for row in rows:
                    canonical_id = row[-1]
                    if previous is not None and canonical_id != previous:
                        entity = self.store.assemble(statements)
                        if entity is not None:
                            if (
                                include_schemata is None
                                or entity.schema in include_schemata
                            ):
                                yield entity
                        statements = []
                    previous = canonical_id
                    statements.append(_statement(row[:-1], canonical_id))
            if len(statements) > 0:
                entity = self.store.assemble(statements)
                if entity is not None:
                    if include_schemata is None or entity.schema in include_schemata:
                        yield entity
        finally:
            cursor.close()
