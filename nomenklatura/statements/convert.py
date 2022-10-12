import orjson
from typing import BinaryIO, Generator, Type
from nomenklatura.statements.model import S

from followthemoney.cli.util import MAX_LINE

# nk entity-statements --format csv/json
# nk statement-entities
# nk migrate/validate


def write_statement(fh: BinaryIO, statement: S) -> None:
    data = statement.to_dict()
    out = orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE)
    fh.write(out)


def read_statements(
    fh: BinaryIO,
    statement_type: Type[S],
    max_line: int = MAX_LINE,
) -> Generator[S, None, None]:
    while line := fh.readline(max_line):
        data = orjson.loads(line)
        yield statement_type.from_dict(data)
