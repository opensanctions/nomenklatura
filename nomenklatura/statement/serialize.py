import csv
import _csv
import click
import orjson
from pathlib import Path
from io import TextIOWrapper
from typing import BinaryIO, TextIO, Generator, Iterable, Type, Dict, Any, List
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


def pack_statement(stmt: S) -> Dict[str, Any]:
    row = stmt.to_row()
    row.pop("canonical_id", None)
    row.pop("prop_type", None)
    prop = row.pop("prop")
    schema = row.pop("schema")
    if prop is None or schema is None:
        raise ValueError("Cannot pack statement without prop and schema")
    row["prop"] = pack_prop(schema, prop)
    return row


def pack_row(stmt: S) -> List[Any]:
    row = stmt.to_row()
    prop = row.pop("prop")
    schema = row.pop("schema")
    if prop is None or schema is None:
        raise ValueError("Cannot pack statement without prop and schema")
    row["prop"] = pack_prop(prop, schema)
    return [row.get(c) for c in PACK_COLUMNS]


def pack_writer(fh: TextIO) -> "_csv._writer":
    return csv.writer(
        fh,
        dialect=csv.unix_dialect,
        quoting=csv.QUOTE_MINIMAL,
    )


def write_pack_statements(fh: BinaryIO, statements: Iterable[S]) -> None:
    with TextIOWrapper(fh, encoding="utf-8") as wrapped:
        writer = pack_writer(wrapped)
        for stmt in statements:
            writer.writerow(pack_row(stmt))


def write_statements(fh: BinaryIO, format: str, statements: Iterable[S]) -> None:
    if format == CSV:
        write_csv_statements(fh, statements)
    elif format == PACK:
        write_pack_statements(fh, statements)
    else:
        write_json_statements(fh, statements)
