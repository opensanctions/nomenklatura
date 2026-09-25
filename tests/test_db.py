from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from followthemoney import Dataset, Statement, StatementEntity
from sqlalchemy import (
    Column,
    MetaData,
    Table,
    Unicode,
    create_engine,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from nomenklatura import settings
from nomenklatura.db import (
    Session,
    get_engine,
    insert_statements,
    make_session,
    make_statement_table,
)


@pytest.mark.parametrize("scheme", ["postgresql", "postgresql+psycopg"])
def test_postgresql_driver(scheme: str) -> None:
    """Both the default and explicit PostgreSQL URLs select psycopg 3."""
    engine = get_engine(f"{scheme}://localhost/nomenklatura")
    assert engine.dialect.driver == "psycopg"


@pytest.mark.parametrize("timestamp", [None, "2026-09-24T12:34:56"])
def test_insert_statements_timestamps(timestamp: str | None) -> None:
    """Bulk loading preserves UTC and NULL timestamps, including in non-UTC sessions.

    It also preserves Unicode and booleans, ignores duplicate rows, and clears
    the dataset when given no statements.
    """
    engine = get_engine()
    tz_engine: Engine | None = None
    if engine.dialect.name == "postgresql":
        # A dedicated engine sets the time zone on every connection it opens,
        # so the load cannot pick up a pooled connection in UTC.
        tz_engine = create_engine(
            settings.DB_URL, connect_args={"options": "-c timezone=Pacific/Honolulu"}
        )
        engine = tz_engine
    table = make_statement_table(MetaData())
    table.create(engine)
    statement = Statement(
        entity_id="person-1",
        prop="name",
        schema="Person",
        value="Müller",
        dataset="timestamps",
        first_seen=timestamp,
        last_seen=timestamp,
        external=True,
    )
    insert_statements(engine, table, "timestamps", [statement, statement], batch_size=1)
    with engine.connect() as conn:
        row = conn.execute(select(table)).one()
    expected = datetime(2026, 9, 24, 12, 34, 56) if timestamp is not None else None
    assert row.first_seen == expected
    assert row.last_seen == expected
    assert row.value == "Müller"
    assert row.external is True
    insert_statements(engine, table, "timestamps", [])
    with engine.connect() as conn:
        assert conn.execute(select(table)).first() is None
    if tz_engine is not None:
        tz_engine.dispose()


def _kv_table(session: Session) -> Table:
    table = Table(
        "kv",
        MetaData(),
        Column("key", Unicode(), primary_key=True),
        Column("value", Unicode()),
    )
    session.create(table)
    return table


def _keys(session: Session, table: Table) -> list[str]:
    return [row.key for row in session.execute(select(table.c.key))]


def test_session_checkpoint_persists_and_continues(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'kv.db'}"
    session = make_session(url)
    table = _kv_table(session)
    session.execute(insert(table).values(key="a", value="1"))
    session.checkpoint()

    other = make_session(url)
    assert "a" in _keys(other, _kv_table(other))
    other.close()

    session.execute(insert(table).values(key="b", value="2"))
    session.commit()
    assert session._conn is None


def test_session_commit_disposes_connection(tmp_path: Path):
    session = make_session(f"sqlite:///{tmp_path / 'kv.db'}")
    table = _kv_table(session)
    conn = session.connection
    session.execute(insert(table).values(key="a", value="1"))
    session.commit()
    assert session._conn is None
    assert conn.closed


def test_session_rollback_discards_but_keeps_connection(tmp_path: Path):
    session = make_session(f"sqlite:///{tmp_path / 'kv.db'}")
    table = _kv_table(session)
    session.checkpoint()  # commit the DDL
    session.execute(insert(table).values(key="a", value="1"))
    session.rollback()
    assert _keys(session, table) == []  # write discarded
    assert session._conn is not None  # connection still usable
    session.close()


def test_session_context_manager_commits_on_clean_exit(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'kv.db'}"
    with make_session(url) as session:
        table = _kv_table(session)
        session.execute(insert(table).values(key="a", value="1"))
    assert session._conn is None

    verify = make_session(url)
    vtable = _kv_table(verify)
    assert _keys(verify, vtable) == ["a"]
    verify.close()


def test_session_context_manager_rolls_back_on_error(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'kv.db'}"
    setup = make_session(url)
    _kv_table(setup)
    setup.commit()

    with pytest.raises(RuntimeError), make_session(url) as session:
        table = Table("kv", MetaData(), autoload_with=session.connection)
        session.execute(insert(table).values(key="a", value="1"))
        raise RuntimeError("boom")
    assert session._conn is None

    verify = make_session(url)
    vtable = Table("kv", MetaData(), autoload_with=verify.connection)
    assert _keys(verify, vtable) == []
    verify.close()


def test_session_dialect(tmp_path: Path):
    session = make_session(f"sqlite:///{tmp_path / 'kv.db'}")
    assert session.dialect.name == "sqlite"
    session.close()


def _parse_statements(
    test_dataset: Dataset, donations_json: list[dict[str, Any]]
) -> Generator[Statement, None, None]:
    for item in donations_json:
        entity = StatementEntity.from_data(test_dataset, item)
        yield from entity.statements


def test_statement_db(test_dataset: Dataset, donations_json: list[dict[str, Any]]):
    engine = get_engine()
    metadata = MetaData()
    table = make_statement_table(metadata)
    metadata.create_all(bind=engine, tables=[table])
    statements = _parse_statements(test_dataset, donations_json)
    insert_statements(engine, table, test_dataset.name, statements)

    with engine.connect() as conn:
        q = select(table)
        cursor = conn.execute(q)
        stmts = list(cursor.fetchall())
        assert len(stmts) > len(donations_json)


def test_insert_statements_sqlite_large_batch(
    test_dataset: Dataset, donations_json: list[dict[str, Any]]
):
    """Verify insert_statements caps batch_size on SQLite to avoid exceeding
    SQLITE_MAX_VARIABLE_NUMBER (32,766 host parameters)."""
    engine = get_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = make_statement_table(metadata)
    metadata.create_all(bind=engine, tables=[table])
    statements = _parse_statements(test_dataset, donations_json)
    # Without the cap, 2857 rows × 14 cols = 39,998 params > 32,766 limit
    insert_statements(engine, table, test_dataset.name, statements, batch_size=10000)

    with engine.connect() as conn:
        q = select(table)
        cursor = conn.execute(q)
        stmts = list(cursor.fetchall())
        assert len(stmts) > len(donations_json)
