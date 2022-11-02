import csv
import click
import orjson
from pathlib import Path
from io import TextIOWrapper
from typing import BinaryIO, Generator, Iterable, Type
from followthemoney.cli.util import MAX_LINE

from nomenklatura.statement.model import S

JSON = "json"
CSV = "csv"
FORMATS = [JSON, CSV]

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

# nk entity-statements --format csv/json
# nk statement-entities
# nk migrate/validate


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


def read_statements(
    fh: BinaryIO, format: str, statement_type: Type[S]
) -> Generator[S, None, None]:
    if format == CSV:
        yield from read_csv_statements(fh, statement_type)
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


def write_json_statement(fh: BinaryIO, statement: S) -> None:
    data = statement.to_dict()
    out = orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE)
    fh.write(out)


def write_json_statements(fh: BinaryIO, statements: Iterable[S]) -> None:
    for stmt in statements:
        write_json_statement(fh, stmt)


def write_csv_statements(fh: BinaryIO, statements: Iterable[S]) -> None:
    with TextIOWrapper(fh, encoding="utf-8") as wrapped:
        writer = csv.writer(wrapped, dialect=csv.unix_dialect)
        writer.writerow(CSV_COLUMNS)
        for stmt in statements:
            row = stmt.to_row()
            writer.writerow([row.get(c) for c in CSV_COLUMNS])


def write_statements(fh: BinaryIO, format: str, statements: Iterable[S]) -> None:
    if format == CSV:
        write_csv_statements(fh, statements)
    else:
        write_json_statements(fh, statements)
