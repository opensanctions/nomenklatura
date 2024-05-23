from pathlib import Path
from typing import Dict, Generator, List, Tuple
from nomenklatura.index.index import Index
import duckdb
import logging

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer

log = logging.getLogger(__name__)


class DuckDBIndex(Index):
    def __init__(self, view: View[DS, CE], path: Path):
        self.view = view
        self.tokenizer = Tokenizer[DS, CE]()
        self.con = duckdb.connect(path.as_posix())
        self.con.execute("CREATE TABLE entries (id TEXT, field TEXT, token TEXT)")

    def index(self, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""

        if not entity.schema.matchable or entity.id is None:
            return
        rows = []

        for field, token in self.tokenizer.entity(entity):
            rows.append([entity.id, field, token])
        self.con.executemany("INSERT INTO entries VALUES (?, ?, ?)", rows)

    def build(self) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.view)
        self.con.execute("BEGIN TRANSACTION")
        for idx, entity in enumerate(self.view.entities()):
            if idx % 10000 == 0:
                log.info("Indexing entity %s", idx)
            self.index(entity)
        self.con.execute("COMMIT")

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        scores: Dict[str, float] = {}
        for field_name, token in self.tokenizer.entity(entity):
            for id, weight in self.frequencies(field_name, token):
                if id not in scores:
                    scores[id] = 0.0
                scores[id] += weight * self.BOOSTS.get(field_name, 1.0)
        scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        for id, score in scores.items():
            yield Identifier.get(id), score

    def frequencies(
        self, field: str, token: str
    ) -> Generator[Tuple[str, float], None, None]:
        # This can probably done with relational query in DuckDB instead of
        # a select per id per token
        mentions_query = """
            SELECT id, count(*) as mentions
            FROM entries
            WHERE field = ? AND token = ?
            GROUP BY id
            """
        field_len_query = """
            SELECT count(*) from entries WHERE field = ? and id = ?
            """
        mentions_result = self.con.execute(mentions_query, [field, token])
        for id, mentions in mentions_result.fetchall():
            (field_len,) = self.con.execute(field_len_query, [field, id]).fetchone()
            field_len = max(1, field_len)
            yield id, mentions / field_len

    def __repr__(self) -> str:
        return "<DuckDBIndex(%r, %r)>" % (
            self.view.scope.name,
            self.con,
        )
