from typing import Any, Generator, List, Optional, Set, Tuple

from followthemoney.property import Property
from sqlalchemy import Table, delete, select
from sqlalchemy.sql.selectable import Select
from sqlalchemy.engine import create_engine, Engine

from nomenklatura import settings
from nomenklatura.dataset import DS
from nomenklatura.db import get_metadata, get_upsert_func
from nomenklatura.entity import CE
from nomenklatura.resolver import Resolver
from nomenklatura.statement import Statement
from nomenklatura.statement.db import make_statement_table
from nomenklatura.statement.serialize import pack_sql_statement
from nomenklatura.store import Store, View, Writer


class SqlStore(Store[DS, CE]):
    def __init__(
        self,
        dataset: DS,
        resolver: Resolver[CE],
        uri: str = settings.DB_URL,
        **engine_kwargs: Any,
    ):
        super().__init__(dataset, resolver)
        if "pool_size" not in engine_kwargs:
            engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
        metadata = get_metadata()
        self.engine: Engine = create_engine(uri, **engine_kwargs)
        self.table = make_statement_table(metadata)
        metadata.create_all(self.engine, tables=[self.table], checkfirst=True)

    def writer(self) -> Writer[DS, CE]:
        return SqlWriter(self)

    def view(self, scope: DS, external: bool = False) -> View[DS, CE]:
        return SqlView(self, scope, external=external)

    def _execute(self, q: Select, many: bool = True) -> Generator[Any, None, None]:
        # execute any read query against sql backend
        with self.engine.connect() as conn:
            if many:
                conn = conn.execution_options(stream_results=True)
                cursor = conn.execute(q)
                while rows := cursor.fetchmany(10_000):
                    yield from rows
            else:
                yield from conn.execute(q)

    def _iterate_stmts(
        self, q: Select, many: bool = True
    ) -> Generator[Statement, None, None]:
        for row in self._execute(q, many=many):
            yield Statement.from_db_row(row)

    def _iterate(self, q: Select, many: bool = True) -> Generator[CE, None, None]:
        current_id = None
        current_stmts: list[Statement] = []
        for stmt in self._iterate_stmts(q, many=many):
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


class SqlWriter(Writer[DS, CE]):
    BATCH_STATEMENTS = 10_000

    def __init__(self, store: SqlStore[DS, CE]):
        self.store: SqlStore[DS, CE] = store
        self.batch: Optional[Set[Statement]] = None
        self.insert = get_upsert_func(self.store.engine)

    def flush(self) -> None:
        if self.batch:
            values = [pack_sql_statement(s) for s in self.batch]
            istmt = self.insert(self.store.table).values(values)
            stmt = istmt.on_conflict_do_update(
                index_elements=["id"],
                set_=dict(
                    canonical_id=istmt.excluded.canonical_id,
                    schema=istmt.excluded.schema,
                    prop_type=istmt.excluded.prop_type,
                    target=istmt.excluded.target,
                    lang=istmt.excluded.lang,
                    original_value=istmt.excluded.original_value,
                    last_seen=istmt.excluded.last_seen,
                ),
            )
            with self.store.engine.begin() as conn:
                conn.execute(stmt)
        self.batch = set()

    def add_statement(self, stmt: Statement) -> None:
        if self.batch is None:
            self.batch = set()
        if stmt.entity_id is None:
            return
        if len(self.batch) >= self.BATCH_STATEMENTS:
            self.flush()
        canonical_id = self.store.resolver.get_canonical(stmt.entity_id)
        stmt.canonical_id = canonical_id
        self.batch.add(stmt)

    def pop(self, entity_id: str) -> List[Statement]:
        self.flush()
        table = self.store.table
        q = select(table).where(table.c.entity_id == entity_id)
        q_delete = delete(table).where(table.c.entity_id == entity_id)
        statements: List[Statement] = list(self.store._iterate_stmts(q))
        with self.store.engine.connect() as conn:
            conn.begin()
            conn.execute(q_delete)
            conn.commit()
        return statements


class SqlView(View[DS, CE]):
    def __init__(
        self, store: SqlStore[DS, CE], scope: DS, external: bool = False
    ) -> None:
        super().__init__(store, scope, external=external)
        self.store: SqlStore[DS, CE] = store

    def get_entity(self, id: str) -> Optional[CE]:
        table = self.store.table
        ids = [str(i) for i in self.store.resolver.connected(id)]
        q = select(table).where(
            table.c.entity_id.in_(ids), table.c.dataset.in_(self.dataset_names)
        )
        for proxy in self.store._iterate(q, many=False):
            return proxy
        return None

    def get_inverted(self, id: str) -> Generator[Tuple[Property, CE], None, None]:
        table = self.store.table
        q = (
            select(table)
            .where(table.c.prop_type == "entity", table.c.value == id)
            .distinct(table.c.value)
        )
        for stmt in self.store._iterate_stmts(q):
            if stmt.canonical_id is not None:
                entity = self.get_entity(stmt.canonical_id)
                if entity is not None:
                    for prop, value in entity.itervalues():
                        if value == id and prop.reverse is not None:
                            yield prop.reverse, entity

    def entities(self) -> Generator[CE, None, None]:
        table: Table = self.store.table
        q = (
            select(table)
            .where(table.c.dataset.in_(self.dataset_names))
            .order_by("canonical_id")
        )
        yield from self.store._iterate(q)
