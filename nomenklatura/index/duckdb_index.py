from pathlib import Path
from typing import Dict, Generator, List, Tuple
from nomenklatura.index.index import Index
import duckdb
import logging
import csv
from functools import lru_cache

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
        self.con = duckdb.connect((path / "duckdb_index.db").as_posix())
        self.con.execute("CREATE TABLE entries (id TEXT, field TEXT, token TEXT)")
        self.path = path

    def dump(self, writer, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""

        if not entity.schema.matchable or entity.id is None:
            return

        for field, token in self.tokenizer.entity(entity):
            writer.writerow([entity.id, field, token])

    def build(self) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.view)
        csv_path = self.path / "mentions.csv"
        with open(csv_path, "w") as fh:
            writer = csv.writer(fh)
            writer.writerow(["id", "field", "token"])
            for idx, entity in enumerate(self.view.entities()):
                self.dump(writer, entity)
                if idx % 10000 == 0:
                    log.info("Dumped %s entities" % idx)

        log.info("Loading data...")
        self.con.execute(f"COPY entries from '{csv_path}'")
        log.info("Index built.")

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        scores: Dict[str, float] = {}
        for field_name, token in self.tokenizer.entity(entity):
            for id, weight in self.frequencies(field_name, token):
                if id not in scores:
                    scores[id] = 0.0
                scores[id] += weight * self.BOOSTS.get(field_name, 1.0)
        scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(Identifier.get(i), w) for i, w in scores]

    @lru_cache(maxsize=10000)
    def frequencies(self, field: str, token: str) -> List[Tuple[str, float]]:

        mentions_query = """
            SELECT id, count(*) as mentions
            FROM entries
            WHERE field = ? AND token = ?
            GROUP BY id
        """
        mentions_rel = self.con.sql(
            mentions_query, alias="mentions", params=[field, token]
        )
        field_len_query = """
            SELECT id, count(*) as field_len from entries
            WHERE field = ?
            GROUP BY id
        """
        field_len_rel = self.con.sql(field_len_query, alias="field_len", params=[field])
        joined = mentions_rel.join(
            field_len_rel, "mentions.id = field_len.id"
        ).set_alias("joined")
        # TODO: Do I really need the max(1, field_len) here?
        weights = self.con.sql("SELECT id, mentions / field_len from joined")
        return list(weights.fetchall())

    def __repr__(self) -> str:
        return "<DuckDBIndex(%r, %r)>" % (
            self.view.scope.name,
            self.con,
        )
