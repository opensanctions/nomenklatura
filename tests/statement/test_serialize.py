from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from followthemoney import model

from nomenklatura.entity import CompositeEntity
from nomenklatura.statement import write_statements, read_statements
from nomenklatura.statement import read_path_statements
from nomenklatura.statement.statement import Statement
from nomenklatura.statement.serialize import CSV, JSON


EXAMPLE = {
    "id": "bla",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}


def test_json_statements():
    buffer = BytesIO()
    entity = CompositeEntity.from_dict(model, EXAMPLE)

    write_statements(buffer, JSON, entity.statements)
    buffer.seek(0)
    stmts = list(read_statements(buffer, JSON, Statement))
    assert len(stmts) == 3
    for stmt in stmts:
        assert stmt.canonical_id == "bla", stmt
        assert stmt.entity_id == "bla", stmt
        assert stmt.schema == "Person", stmt


def test_csv_statements():
    with TemporaryDirectory() as tmpdir:
        entity = CompositeEntity.from_dict(model, EXAMPLE)
        path = Path(tmpdir) / "statement.csv"
        with open(path, "wb") as fh:
            write_statements(fh, CSV, entity.statements)
        stmts = list(read_path_statements(path, CSV, Statement))
        assert len(stmts) == 3, stmts
        for stmt in stmts:
            assert stmt.canonical_id == "bla", stmt
            assert stmt.entity_id == "bla", stmt
            assert stmt.schema == "Person", stmt
