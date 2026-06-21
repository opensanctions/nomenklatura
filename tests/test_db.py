from pathlib import Path
from typing import List, Dict, Any, Generator
import pytest
from sqlalchemy import Column, MetaData, Table, Unicode, insert, select
from followthemoney import Dataset, Statement, StatementEntity

from nomenklatura.db import get_engine, make_session, Session
from nomenklatura.db import make_statement_table, insert_statements


def _kv_table(session: Session) -> Table:
    table = Table(
        "kv",
        MetaData(),
        Column("key", Unicode(), primary_key=True),
        Column("value", Unicode()),
    )
    session.create(table)
    return table


def _keys(session: Session, table: Table) -> List[str]:
    return [row.key for row in session.execute(select(table.c.key))]


def test_session_checkpoint_persists_and_continues(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'kv.db'}"
    session = make_session(url)
    table = _kv_table(session)
    session.execute(insert(table).values(key="a", value="1"))
    session.checkpoint()

    # A fresh connection sees the committed row...
    other = make_session(url)
    assert "a" in _keys(other, _kv_table(other))
    other.close()

    # ...and the original session keeps working without a manual begin.
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
    # Create + commit the table first so the rollback below only drops the row.
    setup = make_session(url)
    _kv_table(setup)
    setup.commit()

    with pytest.raises(RuntimeError):
        with make_session(url) as session:
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
    test_dataset: Dataset, donations_json: List[Dict[str, Any]]
) -> Generator[Statement, None, None]:
    for item in donations_json:
        entity = StatementEntity.from_data(test_dataset, item)
        yield from entity.statements


def test_statement_db(test_dataset: Dataset, donations_json: List[Dict[str, Any]]):
    engine = get_engine("sqlite:///:memory:")
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
    test_dataset: Dataset, donations_json: List[Dict[str, Any]]
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
