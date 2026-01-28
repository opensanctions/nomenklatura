from typing import List, Dict, Any, Generator
from sqlalchemy import MetaData, select
from followthemoney import Dataset, Statement, StatementEntity

from nomenklatura.db import get_engine
from nomenklatura.db import make_statement_table, insert_statements


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
