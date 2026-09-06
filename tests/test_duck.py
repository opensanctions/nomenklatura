import pytest

from nomenklatura import duck

STATEMENT_DDL = ", ".join(
    f'"{name}" {type_}' for name, type_ in duck.STATEMENT_COLUMNS.items()
)


def test_connect_defaults() -> None:
    conn = duck.connect()
    row = conn.execute("SELECT current_setting('preserve_insertion_order')").fetchone()
    assert row is not None and row[0] is False
    query = "SELECT current_setting('disabled_compression_methods')"
    row = conn.execute(query).fetchone()
    assert row is not None and row[0] == "FSST"
    # Cursors must inherit it, since the store reads through them:
    row = conn.cursor().execute(query).fetchone()
    assert row is not None and row[0] == "FSST"
    conn.close()


def test_connect_tuned(tmp_path) -> None:
    conn = duck.connect(tmp_path / "test.duckdb", memory_mb="500", threads=2)
    row = conn.execute("SELECT current_setting('threads')").fetchone()
    assert row is not None and int(row[0]) == 2
    row = conn.execute("SELECT current_setting('memory_limit')").fetchone()
    assert row is not None and "MiB" in row[0]
    conn.close()


def test_validate_statement_relation() -> None:
    conn = duck.connect()
    conn.execute(f"CREATE TABLE stmts ({STATEMENT_DDL})")
    duck.validate_statement_relation(conn, "stmts")

    # Also accepts views over a conforming shape:
    conn.execute("CREATE VIEW stmts_view AS SELECT * FROM stmts")
    duck.validate_statement_relation(conn, "stmts_view")

    conn.execute("CREATE TABLE missing AS SELECT * EXCLUDE (dataset) FROM stmts")
    with pytest.raises(ValueError, match="missing column 'dataset'"):
        duck.validate_statement_relation(conn, "missing")

    conn.execute(
        "CREATE TABLE mistyped AS "
        "SELECT * REPLACE (CAST(first_seen AS VARCHAR) AS first_seen) FROM stmts"
    )
    with pytest.raises(ValueError, match="'first_seen' is VARCHAR"):
        duck.validate_statement_relation(conn, "mistyped")

    with pytest.raises(ValueError, match="Invalid relation name"):
        duck.validate_statement_relation(conn, "stmts; DROP TABLE stmts")
    conn.close()
