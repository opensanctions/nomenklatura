import csv
from io import TextIOWrapper
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Generator, Iterable, List, Optional, TextIO, Type

import click
import orjson
from followthemoney.cli.util import MAX_LINE

from nomenklatura.statement.statement import S
from nomenklatura.util import unpack_prop

JSON = "json"
CSV = "csv"
PACK = "pack"
FORMATS = [JSON, CSV, PACK]

CSV_BATCH = 5000
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
        wrapped = TextIOWrapper(fh, encoding="utf-8")
        return CSVStatementWriter(wrapped)
    elif format == PACK:
        wrapped = TextIOWrapper(fh, encoding="utf-8")
        return PackStatementWriter(wrapped)
    elif format == JSON:
        return JSONStatementWriter(fh)
    raise RuntimeError("Unknown statement format: %s" % format)


def write_statements(fh: BinaryIO, format: str, statements: Iterable[S]) -> None:
    writer = get_statement_writer(fh, format)
    for stmt in statements:
        writer.write(stmt)
    writer.close()


class StatementWriter(object):
    def write(self, stmt: S) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()

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
    def __init__(self, fh: BinaryIO) -> None:
        self.fh = fh

    def write(self, stmt: S) -> None:
        data = stmt.to_dict()
        out = orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE)
        self.fh.write(out)

    def close(self) -> None:
        self.fh.close()


class CSVStatementWriter(StatementWriter):
    def __init__(self, fh: TextIO) -> None:
        self.fh = fh
        self.writer = csv.writer(self.fh, dialect=csv.unix_dialect)
        self.writer.writerow(CSV_COLUMNS)
        self._batch: List[List[Optional[str]]] = []

    def write(self, stmt: S) -> None:
        row = stmt.to_csv_row()
        self._batch.append([row[c] for c in CSV_COLUMNS])
        if len(self._batch) >= CSV_BATCH:
            self.writer.writerows(self._batch)
            self._batch.clear()

    def close(self) -> None:
        if len(self._batch) > 0:
            self.writer.writerows(self._batch)
        self.fh.close()


class PackStatementWriter(StatementWriter):
    def __init__(self, fh: TextIO) -> None:
        self.fh = fh
        self.writer = csv.writer(
            self.fh,
            dialect=csv.unix_dialect,
            quoting=csv.QUOTE_MINIMAL,
        )
        self._batch: List[List[Optional[str]]] = []

    def write(self, stmt: S) -> None:
        # HACK: This is very similar to the CSV writer, but at the very inner
        # loop of the application, so we're duplicating code here.
        target_value: Optional[str] = "t" if stmt.target else "f"
        if stmt.target is None:
            target_value = None
        external_value: Optional[str] = "t" if stmt.external else "f"
        if stmt.external is None:
            external_value = None
        row = [
            stmt.entity_id,
            f"{stmt.schema}:{stmt.prop}",
            stmt.value,
            stmt.dataset,
            stmt.lang,
            stmt.original_value,
            target_value,
            external_value,
            stmt.first_seen,
            stmt.last_seen,
        ]
        self._batch.append(row)
        if len(self._batch) >= CSV_BATCH:
            self.writer.writerows(self._batch)
            self._batch.clear()

    def close(self) -> None:
        if len(self._batch) > 0:
            self.writer.writerows(self._batch)
        self.fh.close()
