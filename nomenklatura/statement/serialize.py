import csv
from io import TextIOWrapper
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Generator, Iterable, List, Optional, Type

import click
import orjson
from followthemoney.cli.util import MAX_LINE

from nomenklatura.statement.statement import S
from nomenklatura.util import pack_prop, unpack_prop

JSON = "json"
CSV = "csv"
PACK = "pack"
FORMATS = [JSON, CSV, PACK]

CSV_COLUMNS = [
    "canonical_id",
    "entity_id",
    "prop",
    "prop_type",
    "schema",
    "value",
    "dataset",
    "lang",
    "original_value",
    "target",
    "external",
    "first_seen",
    "last_seen",
    "id",
]

PACK_COLUMNS = [
    "entity_id",
    "prop",
    "value",
    "dataset",
    "lang",
    "original_value",
    "target",
    "external",
    "first_seen",
    "last_seen",
    "id",
]


def read_json_statements(
    fh: BinaryIO,
    statement_type: Type[S],
    max_line: int = MAX_LINE,
) -> Generator[S, None, None]:
    while line := fh.readline(max_line):
        data = orjson.loads(line)
        yield statement_type.from_dict(data)


def read_csv_statements(
    fh: BinaryIO, statement_type: Type[S]
) -> Generator[S, None, None]:
    wrapped = TextIOWrapper(fh, encoding="utf-8")
    for row in csv.DictReader(wrapped, dialect=csv.unix_dialect):
        yield statement_type.from_row(row)


def unpack_row(row: List[str], statement_type: Type[S]) -> S:
    data = dict(zip(PACK_COLUMNS, row))
    data["canonical_id"] = data["entity_id"]
    schema, prop_type, prop = unpack_prop(data["prop"])
    data["schema"] = schema
    data["prop"] = prop
    data["prop_type"] = prop_type
    return statement_type.from_row(data)


def read_pack_statements(
    fh: BinaryIO, statement_type: Type[S]
) -> Generator[S, None, None]:
    wrapped = TextIOWrapper(fh, encoding="utf-8")
    for row in csv.reader(wrapped, dialect=csv.unix_dialect):
        yield unpack_row(row, statement_type)


def read_statements(
    fh: BinaryIO, format: str, statement_type: Type[S]
) -> Generator[S, None, None]:
    if format == CSV:
        yield from read_csv_statements(fh, statement_type)
    elif format == PACK:
        yield from read_pack_statements(fh, statement_type)
    else:
        yield from read_json_statements(fh, statement_type)


def read_path_statements(
    path: Path, format: str, statement_type: Type[S]
) -> Generator[S, None, None]:
    if str(path) == "-":
        fh = click.get_binary_stream("stdin")
        yield from read_statements(fh, format=format, statement_type=statement_type)
        return
    with open(path, "rb") as fh:
        yield from read_statements(fh, format=format, statement_type=statement_type)


def get_statement_writer(fh: BinaryIO, format: str) -> "StatementWriter":
    if format == CSV:
        return CSVStatementWriter(fh)
    elif format == PACK:
        return PackStatementWriter(fh)
    elif format == JSON:
        return JSONStatementWriter(fh)
    raise RuntimeError("Unknown statement format: %s" % format)


def write_statements(fh: BinaryIO, format: str, statements: Iterable[S]) -> None:
    writer = get_statement_writer(fh, format)
    for stmt in statements:
        writer.write(stmt)
    writer.close()


class StatementWriter(object):
    def __init__(self, fh: BinaryIO) -> None:
        self.fh = fh

    def write(self, stmt: S) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        self.fh.close()

    def __enter__(self) -> "StatementWriter":
        return self

    def __exit__(
        self,
        type: Optional[Type[BaseException]],
        value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()


class JSONStatementWriter(StatementWriter):
    def write(self, stmt: S) -> None:
        data = stmt.to_dict()
        out = orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE)
        self.fh.write(out)


class CSVStatementWriter(StatementWriter):
    def __init__(self, fh: BinaryIO) -> None:
        super().__init__(fh)
        self.wrapper = TextIOWrapper(fh, encoding="utf-8")
        self.writer = csv.writer(self.wrapper, dialect=csv.unix_dialect)
        self.writer.writerow(CSV_COLUMNS)

    def write(self, stmt: S) -> None:
        row = stmt.to_csv_row()
        self.writer.writerow([row.get(c) for c in CSV_COLUMNS])

    def close(self) -> None:
        self.wrapper.close()
        super().close()


class PackStatementWriter(StatementWriter):
    def __init__(self, fh: BinaryIO) -> None:
        super().__init__(fh)
        self.wrapper = TextIOWrapper(fh, encoding="utf-8")
        self.writer = csv.writer(
            self.wrapper,
            dialect=csv.unix_dialect,
            quoting=csv.QUOTE_MINIMAL,
        )

    def write(self, stmt: S) -> None:
        row = stmt.to_csv_row()
        prop = row.pop("prop")
        schema = row.pop("schema")
        if prop is None or schema is None:
            raise ValueError("Cannot pack statement without prop and schema")
        row["prop"] = pack_prop(schema, prop)
        self.writer.writerow([row.get(c) for c in PACK_COLUMNS])

    def close(self) -> None:
        self.wrapper.close()
        super().close()
