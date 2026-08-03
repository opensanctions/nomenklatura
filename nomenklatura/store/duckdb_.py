#
# Read-only statement store on top of a DuckDB relation.
#
# The caller hands the store an open DuckDB connection and the name of a
# relation (table or view) containing statements with source entity ids. Where
# that relation points — local parquet files, remote artifacts, a materialized
# table — is entirely the caller's concern. Canonicalisation comes from the
# Linker: its mapping is registered as a table at init and joined onto the
# statement relation, so long-lived statement artifacts stay usable as the
# resolver evolves.
#
import re
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Tuple

import duckdb
from followthemoney import DS, SE, Property, Schema, Statement, model, registry

from nomenklatura.resolver import Linker
from nomenklatura.store.base import Store, View, Writer

CANONICAL_TABLE = "nk_canonical"
RESOLVED_TABLE = "nk_statements"
EDGES_TABLE = "nk_edges"
ENTITY_PROPS_TABLE = "nk_entity_props"
RELATION_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
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
    (e.g. parquet files) instead of first syncing a mutable store. Two modes:
    the default declares the resolved statements as a view over the caller's
    relation — zero build cost, right for one-shot scans. With
    ``materialize=True`` the resolved statements are copied into a table
    sorted on canonical_id and indexed — pay seconds per few million
    statements once, then point reads are index probes; right for long-lived
    or read-heavy consumers. Bulk access should go through
    `View.get_entities` either way — per-id reads pay a full query each in
    view mode.
    """

    def __init__(
        self,
        dataset: DS,
        linker: Linker[SE],
        conn: duckdb.DuckDBPyConnection,
        relation: str,
        materialize: bool = False,
    ) -> None:
        super().__init__(dataset, linker)
        if RELATION_NAME.match(relation) is None:
            raise ValueError(f"Invalid relation name: {relation!r}")
        self.conn = conn
        self.relation = relation
        self.materialized = materialize
        # Fails loudly if the relation is missing or lacks expected columns:
        conn.execute(f"SELECT {STMT_COLUMNS} FROM {relation} s LIMIT 0")
        self._load_canonical()
        self._load_resolved()
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

    def _load_resolved(self) -> None:
        """Expose the caller's relation with a canonical_id column attached.

        In view mode this is free; queries resolve through the join at read
        time. In materialized mode the join result is copied into a table
        sorted on canonical_id (clustered row groups for scans, zone-map
        pruning for point reads) with an index on top."""
        select = (
            f"SELECT {RAW_COLUMNS}, "
            f"coalesce(c.canonical_id, s.entity_id) AS canonical_id "
            f"FROM {self.relation} s "
            f"LEFT JOIN {CANONICAL_TABLE} c ON c.entity_id = s.entity_id"
        )
        if self.materialized:
            self.conn.execute(
                f"CREATE OR REPLACE TABLE {RESOLVED_TABLE} AS "
                f"{select} ORDER BY canonical_id"
            )
            self.conn.execute(
                f"CREATE INDEX {RESOLVED_TABLE}_canonical "
                f"ON {RESOLVED_TABLE} (canonical_id)"
            )
        else:
            self.conn.execute(f"CREATE OR REPLACE VIEW {RESOLVED_TABLE} AS {select}")

    def _load_edges(self) -> None:
        """Materialize entity-typed property rows into a resolved edge table.

        One scan of the resolved relation and a mapping join on the value
        side produce (origin, value) pairs with both source and canonical
        ids, so inverted lookups and graph traversal are single probes
        instead of per-read referent expansion."""
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
                s.canonical_id AS origin_canonical_id,
                s.dataset AS dataset,
                s.external AS external
            FROM {RESOLVED_TABLE} s
            JOIN {ENTITY_PROPS_TABLE} p
                ON p."schema" = s."schema" AND p.prop = s.prop
            LEFT JOIN {CANONICAL_TABLE} cv ON cv.entity_id = s.value
            """
        )

    def writer(self) -> Writer[DS, SE]:
        raise NotImplementedError("DuckDBStore is read-only")

    def update(self, id: str) -> None:
        # Canonicalisation is frozen when the linker mapping is registered at
        # init; merges decided later become visible by constructing a fresh
        # store. The base implementation rewrites store keys via the writer;
        # there is nothing to rewrite here.
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

    def _lookup(self, ids: Iterable[str]) -> Tuple[str, Set[str]]:
        """Pick the point-read strategy for the store's mode.

        The materialized table probes its canonical_id index directly. The
        view must not: a predicate on the computed canonical_id column cannot
        push down into the underlying scan (no zone maps, no bloom filters),
        so there the cluster is expanded to referents in Python and probed on
        the source entity_id column."""
        lookup: Set[str] = set()
        if self.store.materialized:
            for id in ids:
                lookup.add(self.store.linker.get_canonical(id))
            return "canonical_id", lookup
        for id in ids:
            lookup.update(self.store.linker.get_referents(id, canonicals=True))
            lookup.add(id)
        return "entity_id", lookup

    def has_entity(self, id: str) -> bool:
        column, lookup = self._lookup([id])
        holes = ", ".join("?" for _ in lookup)
        cursor = self.store.conn.cursor()
        try:
            row = cursor.execute(
                f"SELECT 1 FROM {RESOLVED_TABLE} s "
                f"WHERE s.{column} IN ({holes}) AND {self._filters()} LIMIT 1",
                list(lookup),
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
        column, lookup = self._lookup(ids)
        if len(lookup) == 0:
            return
        holes = ", ".join("?" for _ in lookup)
        clusters: Dict[str, List[Statement]] = {}
        cursor = self.store.conn.cursor()
        try:
            result = cursor.execute(
                f"SELECT {STMT_COLUMNS}, s.canonical_id FROM {RESOLVED_TABLE} s "
                f"WHERE s.{column} IN ({holes}) AND {self._filters()}",
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
            f"SELECT {STMT_COLUMNS}, s.canonical_id FROM {RESOLVED_TABLE} s "
            f"WHERE {self._filters()} "
            f"ORDER BY s.canonical_id"
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
