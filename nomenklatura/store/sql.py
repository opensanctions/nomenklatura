from typing import Any, Generator, List, Optional, Set, Tuple

from followthemoney import DS, SE, Property, Schema, Statement
from sqlalchemy import Table, delete, func, select
from sqlalchemy.engine import Engine, Transaction, create_engine
from sqlalchemy.dialects.postgresql import insert as psql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.sql.selectable import Select

from nomenklatura import settings
from nomenklatura.db import get_metadata
from nomenklatura.resolver import Linker, Identifier
from nomenklatura.db import make_statement_table
from nomenklatura.store import Store, View, Writer


class SQLStore(Store[DS, SE]):
    def __init__(
        self,
        dataset: DS,
        linker: Linker[SE],
        uri: str = settings.DB_URL,
        **engine_kwargs: Any,
    ):
        super().__init__(dataset, linker)
        if "pool_size" not in engine_kwargs:
            engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
        # if uri.lower().startswith("sqlite"):
        #     engine_kwargs.pop("pool_size", None)
        metadata = get_metadata()
        self.engine: Engine = create_engine(uri, **engine_kwargs)
        self.table = make_statement_table(metadata)
        metadata.create_all(self.engine, tables=[self.table], checkfirst=True)

    def writer(self) -> Writer[DS, SE]:
        return SQLWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, SE]:
        return SQLView(self, scope, external=external)

    def _execute(
        self, q: Select[Any], stream: bool = True
    ) -> Generator[Any, None, None]:
        # execute any read query against sql backend
        with self.engine.connect() as conn:
            if stream:
                conn = conn.execution_options(stream_results=True)
            cursor = conn.execute(q)
            while rows := cursor.fetchmany(10_000):
                yield from rows

    def _iterate_stmts(
        self, q: Select[Any], stream: bool = True
    ) -> Generator[Statement, None, None]:
        for row in self._execute(q, stream=stream):
            yield Statement.from_db_row(row)

    def _iterate(
        self, q: Select[Any], stream: bool = True
    ) -> Generator[SE, None, None]:
        current_id = None
        current_stmts: list[Statement] = []
        for stmt in self._iterate_stmts(q, stream=stream):
            entity_id = stmt.entity_id
            if current_id is None:
                current_id = entity_id
            if current_id != entity_id:
                proxy = self.assemble(current_stmts)
                if proxy is not None:
                    yield proxy
                current_id = entity_id
                current_stmts = []
            current_stmts.append(stmt)
        if len(current_stmts):
            proxy = self.assemble(current_stmts)
            if proxy is not None:
                yield proxy


class SQLWriter(Writer[DS, SE]):
    BATCH_STATEMENTS = 10_000

    def __init__(self, store: SQLStore[DS, SE]):
        self.store: SQLStore[DS, SE] = store
        self.batch: Set[Statement] = set()
        self.conn = self.store.engine.connect()
        self.tx: Optional[Transaction] = None

    def _upsert_batch(self) -> None:
        if not len(self.batch):
            return
        values = [s.to_db_row() for s in self.batch]
        if self.tx is None:
            self.tx = self.conn.begin()
        if self.store.engine.dialect.name == "sqlite":
            ilstmt = sqlite_insert(self.store.table).values(values)
            lstmt = ilstmt.on_conflict_do_update(
                index_elements=["id"],
                set_=dict(
                    canonical_id=ilstmt.excluded.canonical_id,
                    schema=ilstmt.excluded.schema,
                    prop_type=ilstmt.excluded.prop_type,
                    lang=ilstmt.excluded.lang,
                    original_value=ilstmt.excluded.original_value,
                    last_seen=ilstmt.excluded.last_seen,
                ),
            )
            self.conn.execute(lstmt)
        elif self.store.engine.dialect.name in ("postgresql", "postgres"):
            ipstmt = psql_insert(self.store.table).values(values)
            pstmt = ipstmt.on_conflict_do_update(
                index_elements=["id"],
                set_=dict(
                    canonical_id=ipstmt.excluded.canonical_id,
                    schema=ipstmt.excluded.schema,
                    prop_type=ipstmt.excluded.prop_type,
                    lang=ipstmt.excluded.lang,
                    original_value=ipstmt.excluded.original_value,
                    last_seen=ipstmt.excluded.last_seen,
                ),
            )
            self.conn.execute(pstmt)
        else:
            msg = f"Upsert not implemented for dialect {self.store.engine.dialect.name}"
            raise NotImplementedError(msg)
        self.batch = set()

    def flush(self) -> None:
        if len(self.batch):
            self._upsert_batch()
        if self.tx is not None:
            self.tx.commit()
            self.tx = None

    def add_statement(self, stmt: Statement) -> None:
        if stmt.entity_id is None:
            return
        canonical_id = self.store.linker.get_canonical(stmt.entity_id)
        stmt.canonical_id = canonical_id
        self.batch.add(stmt)
        if len(self.batch) >= self.BATCH_STATEMENTS:
            self._upsert_batch()

    def pop(self, entity_id: str) -> List[Statement]:
        if self.tx is None:
            self.tx = self.conn.begin()

        table = self.store.table
        q = select(table)
        q = q.where(table.c.canonical_id == entity_id)
        statements: List[Statement] = []
        cursor = self.conn.execute(q)
        for row in cursor.fetchall():
            statements.append(Statement.from_db_row(row))

        q_delete = delete(table)
        q_delete = q_delete.where(table.c.canonical_id == entity_id)
        self.conn.execute(q_delete)
        return statements


class SQLView(View[DS, SE]):
    def __init__(
        self, store: SQLStore[DS, SE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: SQLStore[DS, SE] = store

    def get_entity(self, id: str) -> Optional[SE]:
        table = self.store.table
        q = select(table)
        q = q.where(table.c.canonical_id == id)
        q = q.where(table.c.dataset.in_(self.dataset_names))
        for proxy in self.store._iterate(q, stream=False):
            return proxy
        return None

    def has_entity(self, id: str) -> bool:
        table = self.store.table
        q = select(func.count(table.c.id))
        q = q.where(table.c.canonical_id == id)
        q = q.where(table.c.dataset.in_(self.dataset_names))
        with self.store.engine.connect() as conn:
            cursor = conn.execute(q)
            count = cursor.scalar()
            if count is not None and count > 0:
                return True
            else:
                return False

    def get_inverted(self, id: str) -> Generator[Tuple[Property, SE], None, None]:
        table = self.store.table
        id_ = Identifier.get(id)
        ids = [i.id for i in self.store.linker.connected(id_)]
        q = select(table.c.canonical_id)
        q = q.where(table.c.prop_type == "entity")
        q = q.where(table.c.value.in_(ids))
        q = q.where(table.c.dataset.in_(self.dataset_names))
        q = q.group_by(table.c.canonical_id)
        with self.store.engine.connect() as conn:
            cursor = conn.execute(q)
            for (canonical_id,) in cursor.fetchall():
                if canonical_id is None:
                    continue
                entity = self.get_entity(canonical_id)
                if entity is not None:
                    for prop, value in entity.itervalues():
                        if value == id and prop.reverse is not None:
                            yield prop.reverse, entity

    def entities(self, include_schemata: Optional[List[Schema]] = None) -> Generator[SE, None, None]:
        table: Table = self.store.table
        q = select(table)
        q = q.where(table.c.dataset.in_(self.dataset_names))
        q = q.order_by(table.c.canonical_id)
        for entity in self.store._iterate(q, stream=True):
            if include_schemata is not None and entity.schema not in include_schemata:
                continue
            yield entity
