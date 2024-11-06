from collections import defaultdict
import csv
from pathlib import Path
import logging
from itertools import combinations
from tempfile import mkdtemp
from typing import Any, Dict, Generator, List, Set, Tuple
from followthemoney.types import registry
import duckdb

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer
from nomenklatura.index.common import BaseIndex

log = logging.getLogger(__name__)


class DuckDBIndex(BaseIndex[DS, CE]):
    """
    An in-memory search index to match entities against a given dataset.

    For each field in the dataset, the index stores the IDs which contains each
    token, along with the absolute frequency of each token in the document.
    """

    name = "duckdb"

    BOOSTS = {
        NAME_PART_FIELD: 2.0,
        WORD_FIELD: 0.5,
        registry.name.name: 10.0,
        # registry.country.name: 1.5,
        # registry.date.name: 1.5,
        # registry.language: 0.7,
        # registry.iban.name: 3.0,
        registry.phone.name: 3.0,
        registry.email.name: 3.0,
        # registry.entity: 0.0,
        # registry.topic: 2.1,
        registry.address.name: 2.5,
        registry.identifier.name: 3.0,
    }

    __slots__ = "view", "fields", "tokenizer", "entities"

    def __init__(self, view: View[DS, CE], data_dir: Path):
        self.view = view
        self.tokenizer = Tokenizer[DS, CE]()
        self.path = Path(mkdtemp())
        self.con = duckdb.connect((self.path / "duckdb_index.db").as_posix())
        self.con.execute("SET memory_limit = '2GB';")
        self.con.execute("SET max_memory = '2GB';")
        self.con.execute("SET threads = 1;")
        self.con.execute("CREATE TABLE entries (id TEXT, field TEXT, token TEXT)")

    def dump(self, writer, entity: CE) -> None:

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

    def pairs(self, max_pairs: int = BaseIndex.MAX_PAIRS) -> List[Tuple[Pair, float]]:
        csv_path = self.path / "cooccurrences.csv"
        with open(csv_path, "w") as fh:
            writer = csv.writer(fh)
            writer.writerow(["left", "right", "score"])
            for pair, score in self.cooccurring_tokens():
                writer.writerow([pair[0], pair[1], score])
        log.info("Loading co-occurrences...")
        self.con.execute('CREATE TABLE cooccurrences ("left" TEXT, "right" TEXT, score FLOAT)')
        self.con.execute(f"COPY cooccurrences from '{csv_path}'")
        pairs_query = """
            SELECT "left", "right", sum(score) as score
            FROM cooccurrences
            GROUP BY "left", "right"
            ORDER BY score DESC
            LIMIT ?
        """
        pairs_rel = self.con.execute(pairs_query, [max_pairs])
        pairs: List[Tuple[Pair, float]] = []
        for left, right, score in pairs_rel.fetchall():
            pairs.append(((Identifier.get(left), Identifier.get(right)), score))
        return pairs

    def cooccurring_tokens(self):
        logged = defaultdict(int)
        for field_name, token, entities in self.frequencies():
            logged[field_name] += 1
            if logged[field_name] % 10000 == 0:
                log.info("Pairwise xref [%s]: %d" % (field_name, logged[field_name]))
            boost = self.BOOSTS.get(field_name, 1.0)
            for (left, lw), (right, rw) in combinations(entities, 2):
                if lw == 0.0 or rw == 0.0:
                    continue
                pair = (max(left, right), min(left, right))
                score = (lw + rw) * boost
                yield pair, score

    def frequencies(
        self,
    ) -> Generator[Tuple[str, str, List[Tuple[Identifier, float]]], None, None]:
        field_len_query = """
            SELECT field, id, count(*) as field_len from entries
            GROUP BY field, id
        """
        field_len = self.con.sql(field_len_query)
        mentions_query = """
            SELECT field, id, token, count(*) as mentions
            FROM entries
            GROUP BY field, id, token
        """
        mentions = self.con.sql(mentions_query)
        token_freq_query = """
            SELECT field, token, count(*) as token_freq
            FROM entries
            GROUP BY field, token
        """
        token_freq = self.con.sql(token_freq_query)
        query = """
            SELECT mentions.field, mentions.token, mentions.id, mentions/field_len
            FROM field_len
            JOIN mentions
            ON field_len.field = mentions.field AND field_len.id = mentions.id
            JOIN token_freq
            ON token_freq.field = mentions.field AND token_freq.token = mentions.token
            where token_freq < 100
            ORDER BY mentions.field, mentions.token
        """
        rel = self.con.sql(query)
        row = rel.fetchone()
        entities = []  # the entities in this field, token group
        field_name = None
        token = None
        while row is not None:
            field_name, token, id, freq = row
            entities.append((Identifier.get(id), freq))

            row = rel.fetchone()
            if row is None:
                yield field_name, token, entities
                break
            new_field_name, new_token, _, _ = row
            if new_field_name != field_name or new_token != token:
                yield field_name, token, entities
                entities = []

    def __repr__(self) -> str:
        return "<DuckDBIndex(%r, %r)>" % (
            self.view.scope.name,
            self.con,
        )
