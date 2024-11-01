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

        self.calculate_frequencies()
        log.info("Index built.")

    def pairs(self, max_pairs: int = BaseIndex.MAX_PAIRS):
        pairs: Dict[Pair, float] = {}
        for field_name, token, entities in self.frequencies():
            boost = self.BOOSTS.get(field_name, 1.0)
            for (left, lw), (right, rw) in combinations(entities, 2):
                if lw == 0.0 or rw == 0.0:
                    continue
                pair = (max(left, right), min(left, right))
                if pair not in pairs:
                    pairs[pair] = 0
                score = (lw + rw) * boost
                pairs[pair] += score
        return sorted(pairs.items(), key=lambda p: p[1], reverse=True)[:max_pairs]

    def field_lengths(self):
        field_len_query = """
            SELECT field, id, count(*) as field_len from entries
            GROUP BY field, id
            ORDER by field, id
        """
        field_len_rel = self.con.sql(field_len_query, alias="field_len")
        row = field_len_rel.fetchone()
        while row is not None:
            yield row
            row = field_len_rel.fetchone()

    def mentions(self) -> Generator[Tuple[str, str, str, int], None, None]:
        """Yields tuples of (field_name, entity_id, token, mention_count)"""

        mentions_query = """
            SELECT field, id, token, count(*) as mentions
            FROM entries
            GROUP BY field, id, token
            ORDER by field, id, token
        """
        mentions_rel = self.con.sql(mentions_query, alias="mentions")
        row = mentions_rel.fetchone()
        while row is not None:
            yield row
            row = mentions_rel.fetchone()

    def id_grouped_mentions(
        self,
    ) -> Generator[Tuple[str, str, int, List[Tuple[str, int]]], None, None]:
        """
        Yields tuples of (field_name, entity_id, field_len, [(token, mention_count)])
        """
        mentions_gen = self.mentions()
        mention_row = None
        # Read all field lengths into memory because the concurrent iteration
        # sees to be exiting the outer loop early and giving partial results.
        for field_name, id, field_len in list(self.field_lengths()):
            mentions = []
            try:
                if mention_row is None:  # first iteration
                    mention_field_name, mention_id, token, mention_count = next(
                        mentions_gen
                    )

                while mention_field_name == field_name and mention_id == id:
                    mentions.append((token, mention_count))
                    mention_field_name, mention_id, token, mention_count = next(
                        mentions_gen
                    )
                yield field_name, id, field_len, mentions
            except StopIteration:
                yield field_name, id, field_len, mentions
                break

    def calculate_frequencies(self) -> None:
        csv_path = self.path / "frequencies.csv"
        with open(csv_path, "w") as fh:
            writer = csv.writer(fh)
            writer.writerow(["field", "id", "token", "frequency"])

            for field_name, id, field_len, mentions in self.id_grouped_mentions():
                for token, freq in mentions:
                    writer.writerow([field_name, id, token, freq / field_len])

        log.info(f"Loading frequencies data... ({csv_path})")
        self.con.execute(
            "CREATE TABLE frequencies (field TEXT, id TEXT, token TEXT, frequency FLOAT)"
        )
        self.con.execute(f"COPY frequencies from '{csv_path}'")
        log.info("Frequencies are loaded")

    def frequencies(
        self,
    ) -> Generator[Tuple[str, str, List[Tuple[Identifier, float]]], None, None]:
        query = """
            SELECT field, token, id, frequency
            FROM frequencies
            ORDER by field, token
        """
        rel = self.con.sql(query, alias="mentions")
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
