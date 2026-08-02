#
# Read-only statement store on top of a DuckDB relation.
#
# The caller hands the store an open DuckDB connection and the name of a
# relation (table or view) containing statements with source entity ids. Where
# that relation points — local parquet files, remote artifacts, a materialized
# table — is entirely the caller's concern. Canonicalisation happens at read
# time from the Linker, so long-lived statement artifacts stay usable as the
# resolver evolves: point reads expand referents via the in-memory linker,
# scans join against a canonical-id mapping table registered at init.
#
import re
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple

import duckdb
from followthemoney import DS, SE, Property, Schema, Statement, model, registry

from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer

CANONICAL_TABLE = "nk_canonical"
EDGES_TABLE = "nk_edges"
ENTITY_PROPS_TABLE = "nk_entity_props"
RELATION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
FETCH_SIZE = 10_000
INSERT_BATCH = 50_000

STMT_COLUMNS = (
    's.id, s.entity_id, s."schema", s.prop, s.value, s.dataset, s.lang, '
    "s.original_value, s.origin, s.external, "
    "strftime(s.first_seen, '%Y-%m-%dT%H:%M:%S') AS first_seen, "
    "strftime(s.last_seen, '%Y-%m-%dT%H:%M:%S') AS last_seen"
)


def _statement(row: Tuple[Any, ...], canonical_id: str) -> Statement:
    (sid, entity_id, schema, prop, value, dataset, lang, original_value,
     origin, external, first_seen, last_seen) = row
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


class DuckDBStore(Store[DS, SE]):
    """Serve entities out of a DuckDB statement relation, read-only.

    Use this to run consumers like xref off immutable statement artifacts
    (e.g. parquet files) instead of first syncing a mutable store. Bulk access
    must go through `View.get_entities` — per-id reads pay a full query each.
    """

    def __init__(
        self,
        dataset: DS,
        linker: Linker[SE],
        conn: duckdb.DuckDBPyConnection,
        relation: str,
    ) -> None:
        super().__init__(dataset, linker)
        if RELATION_NAME.match(relation) is None:
            raise ValueError(f"Invalid relation name: {relation!r}")
        self.conn = conn
        self.relation = relation
        # Fails loudly if the relation is missing or lacks expected columns:
        conn.execute(f"SELECT {STMT_COLUMNS} FROM {relation} s LIMIT 0")
        self._load_canonical()
        self._load_edges()

    def _load_canonical(self) -> None:
        """Register the linker's canonicalisation as a joinable table.

        A regular (non-temp) table so that per-query cursors see it; temp
        tables are invisible across DuckDB cursor duplicates."""
        self.conn.execute(
            f"CREATE OR REPLACE TABLE {CANONICAL_TABLE} "
            "(entity_id VARCHAR, canonical_id VARCHAR)"
        )
        batch: List[Tuple[str, str]] = []
        for pair in self.linker.iter_pairs():
            batch.append(pair)
            if len(batch) >= INSERT_BATCH:
                self.conn.executemany(
                    f"INSERT INTO {CANONICAL_TABLE} VALUES (?, ?)", batch
                )
                batch.clear()
        if len(batch) > 0:
            self.conn.executemany(
                f"INSERT INTO {CANONICAL_TABLE} VALUES (?, ?)", batch
            )

    def _load_edges(self) -> None:
        """Materialize entity-typed property rows into a resolved edge table.

        One scan and two mapping joins produce (origin, value) pairs with both
        source and canonical ids, so inverted lookups and graph traversal are
        single probes instead of per-read referent expansion."""
        self.conn.execute(
            f"CREATE OR REPLACE TABLE {ENTITY_PROPS_TABLE} "
            '("schema" VARCHAR, prop VARCHAR)'
        )
        pairs: Set[Tuple[str, str]] = set()
        for schema in model.schemata.values():
            for prop in schema.properties.values():
                if prop.type == registry.entity and not prop.stub:
                    pairs.add((schema.name, prop.name))
        self.conn.executemany(
            f"INSERT INTO {ENTITY_PROPS_TABLE} VALUES (?, ?)", sorted(pairs)
        )
        self.conn.execute(
            f"""
            CREATE OR REPLACE TABLE {EDGES_TABLE} AS
            SELECT
                s."schema" AS "schema",
                s.prop AS prop,
                s.value AS value_entity_id,
                coalesce(cv.canonical_id, s.value) AS value_canonical_id,
                s.entity_id AS origin_entity_id,
                coalesce(co.canonical_id, s.entity_id) AS origin_canonical_id,
                s.dataset AS dataset,
                s.external AS external
            FROM {self.relation} s
            JOIN {ENTITY_PROPS_TABLE} p
                ON p."schema" = s."schema" AND p.prop = s.prop
            LEFT JOIN {CANONICAL_TABLE} cv ON cv.entity_id = s.value
            LEFT JOIN {CANONICAL_TABLE} co ON co.entity_id = s.entity_id
            """
        )

    def writer(self) -> Writer[DS, SE]:
        raise NotImplementedError("DuckDBStore is read-only")

    def update(self, id: str) -> None:
        # Canonicalisation is applied at read time, so merges decided while
        # the store is open become visible without rewriting anything. The
        # base implementation rewrites store keys via the writer; there is
        # nothing to rewrite here.
        pass

    def view(self, scope: DS, external: bool = False) -> View[DS, SE]:
        return DuckDBView(self, scope, external=external)

    def close(self) -> None:
        # The connection is owned by the caller; leave it open.
        pass


class DuckDBView(View[DS, SE]):
    def __init__(
        self, store: DuckDBStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: DuckDBStore[DS, SE] = store

    def _filters(self, alias: str = "s") -> str:
        names = ", ".join(f"'{n}'" for n in sorted(self.dataset_names))
        query = f"{alias}.dataset IN ({names})"
        if self.external is False:
            query += f" AND NOT {alias}.external"
        return query

    def _referents(self, id: str) -> Set[str]:
        ids = set(self.store.linker.get_referents(id, canonicals=True))
        ids.add(id)
        return ids

    def has_entity(self, id: str) -> bool:
        ids = self._referents(id)
        holes = ", ".join("?" for _ in ids)
        cursor = self.store.conn.cursor()
        try:
            row = cursor.execute(
                f"SELECT 1 FROM {self.store.relation} s "
                f"WHERE s.entity_id IN ({holes}) AND {self._filters()} LIMIT 1",
                list(ids),
            ).fetchone()
            return row is not None
        finally:
            cursor.close()

    def get_entity(self, id: str) -> Optional[SE]:
        for entity in self.get_entities([id]):
            return entity
        return None

    def get_entities(self, ids: Iterable[str]) -> Generator[SE, None, None]:
        """Fetch a batch of entities in a single query."""
        lookup: Set[str] = set()
        for id in ids:
            lookup.update(self._referents(id))
        if len(lookup) == 0:
            return
        holes = ", ".join("?" for _ in lookup)
        clusters: Dict[str, List[Statement]] = {}
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(
                f"SELECT {STMT_COLUMNS} FROM {self.store.relation} s "
                f"WHERE s.entity_id IN ({holes}) AND {self._filters()}",
                list(lookup),
            )
            while rows := result.fetchmany(FETCH_SIZE):
                for row in rows:
                    canonical_id = self.store.linker.get_canonical(row[1])
                    stmt = _statement(row, canonical_id)
                    clusters.setdefault(canonical_id, []).append(stmt)
        finally:
            cursor.close()
        for statements in clusters.values():
            entity = self.store.assemble(statements)
            if entity is not None:
                yield entity

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        canonical = self.store.linker.get_canonical(id)
        owners: Set[str] = set()
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(
                f"SELECT DISTINCT e.origin_canonical_id FROM {EDGES_TABLE} e "
                f"WHERE e.value_canonical_id = ? AND {self._filters('e')}",
                [canonical],
            )
            while rows := result.fetchmany(FETCH_SIZE):
                owners.update(row[0] for row in rows)
        finally:
            cursor.close()
        for entity in self.get_entities(owners):
            for prop, value in entity.itervalues():
                if value == canonical and prop.reverse is not None:
                    yield prop.reverse, entity

    def entities(
        self, include_schemata: Optional[List[Schema]] = None
    ) -> Generator[SE, None, None]:
        query = (
            f"SELECT {STMT_COLUMNS}, "
            f"coalesce(c.canonical_id, s.entity_id) AS canonical_id "
            f"FROM {self.store.relation} s "
            f"LEFT JOIN {CANONICAL_TABLE} c ON c.entity_id = s.entity_id "
            f"WHERE {self._filters()} "
            f"ORDER BY canonical_id"
        )
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(query)
            statements: List[Statement] = []
            previous: Optional[str] = None
            while rows := result.fetchmany(FETCH_SIZE):
                for row in rows:
                    canonical_id = row[-1]
                    if previous is not None and canonical_id != previous:
                        entity = self.store.assemble(statements)
                        if entity is not None:
                            if include_schemata is None or entity.schema in include_schemata:
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
