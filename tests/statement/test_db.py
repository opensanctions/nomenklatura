from typing import List, Dict, Any, Generator
from sqlalchemy import MetaData, select

from nomenklatura.dataset import Dataset
from nomenklatura.db import get_engine
from nomenklatura.statement import Statement
from nomenklatura.entity import CompositeEntity
from nomenklatura.statement.db import make_statement_table, insert_dataset


def _parse_statements(
    test_dataset: Dataset, donations_json: List[Dict[str, Any]]
) -> Generator[Statement, None, None]:
    for item in donations_json:
        entity = CompositeEntity.from_data(test_dataset, item)
        yield from entity.statements


def test_statement_db(test_dataset: Dataset, donations_json: List[Dict[str, Any]]):
    engine = get_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = make_statement_table(metadata)
    metadata.create_all(bind=engine, tables=[table])
    statements = _parse_statements(test_dataset, donations_json)
    insert_dataset(engine, table, test_dataset.name, statements)

    with engine.connect() as conn:
        q = select(table)
        cursor = conn.execute(q)
        stmts = list(cursor.fetchall())
        assert len(stmts) > len(donations_json)

    get_engine.cache_clear()
