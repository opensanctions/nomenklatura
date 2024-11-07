from duckdb import DuckDBPyRelation
from followthemoney.types import registry
from pathlib import Path
from shutil import rmtree
from typing import Iterable, Tuple
import csv
import duckdb
import logging

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.index.common import BaseIndex
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.store import View

log = logging.getLogger(__name__)

BATCH_SIZE = 1000


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
        self.data_dir = data_dir
        if self.data_dir.exists():
            rmtree(self.data_dir.as_posix())
        self.data_dir.mkdir(parents=True)
        self.con = duckdb.connect((self.data_dir / "duckdb_index.db").as_posix())

        # https://duckdb.org/docs/guides/performance/environment
        # > For ideal performance, aggregation-heavy workloads require approx.
        # > 5 GB memory per thread and join-heavy workloads require approximately
        # > 10 GB memory per thread.
        # > Aim for 5-10 GB memory per thread.
        self.con.execute("SET memory_limit = '2GB';")
        self.con.execute("SET max_memory = '2GB';")
        # > If you have a limited amount of memory, try to limit the number of threads
        self.con.execute("SET threads = 1;")

    def build(self) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.view)
        self.con.execute("CREATE TABLE boosts (field TEXT, boost FLOAT)")
        for field, boost in self.BOOSTS.items():
            self.con.execute("INSERT INTO boosts VALUES (?, ?)", [field, boost])

        self.con.execute("CREATE TABLE entries (id TEXT, field TEXT, token TEXT)")
        csv_path = self.data_dir / "mentions.csv"
        log.info("Dumping entity tokens to CSV for bulk load into the database...")
        with open(csv_path, "w") as fh:
            writer = csv.writer(fh)

            # csv.writer type gymnastics
            def dump_entity(entity: CE) -> None:
                if not entity.schema.matchable or entity.id is None:
                    return
                for field, token in self.tokenizer.entity(entity):
                    writer.writerow([entity.id, field, token])

            writer.writerow(["id", "field", "token"])
            for idx, entity in enumerate(self.view.entities()):
                dump_entity(entity)
                if idx % 10000 == 0:
                    log.info("Dumped %s entities" % idx)

        log.info("Loading data...")
        self.con.execute(f"COPY entries from '{csv_path}'")
        log.info("Index built.")

    def field_len_rel(self) -> DuckDBPyRelation:
        field_len_query = """
            SELECT field, id, count(*) as field_len from entries
            GROUP BY field, id
        """
        return self.con.sql(field_len_query)

    def mentions_rel(self) -> DuckDBPyRelation:
        mentions_query = """
            SELECT field, id, token, count(*) as mentions
            FROM entries
            GROUP BY field, id, token
        """
        return self.con.sql(mentions_query)

    def token_freq_rel(self) -> DuckDBPyRelation:
        token_freq_query = """
            SELECT field, token, count(*) as token_freq
            FROM entries
            GROUP BY field, token
        """
        return self.con.sql(token_freq_query)

    def frequencies_rel(self) -> DuckDBPyRelation:
        field_len = self.field_len_rel()  # noqa
        mentions = self.mentions_rel()  # noqa
        token_freq = self.token_freq_rel()  # noqa
        term_frequencies_query = """
            SELECT mentions.field, mentions.token, mentions.id, mentions/field_len as tf
            FROM field_len
            JOIN mentions
            ON field_len.field = mentions.field AND field_len.id = mentions.id
            JOIN token_freq
            ON token_freq.field = mentions.field AND token_freq.token = mentions.token
            where token_freq < 100
        """
        return self.con.sql(term_frequencies_query)

    def pairs(
        self, max_pairs: int = BaseIndex.MAX_PAIRS
    ) -> Iterable[Tuple[Pair, float]]:
        term_frequencies = self.frequencies_rel()  # noqa
        pairs_query = """
            SELECT "left".id, "right".id, sum(("left".tf + "right".tf) * boost) as score
            FROM term_frequencies as "left"
            JOIN term_frequencies as "right"
            ON "left".field = "right".field AND "left".token = "right".token
            JOIN boosts
            ON "left".field = boosts.field
            WHERE "left".id > "right".id
            GROUP BY "left".id, "right".id
            ORDER BY score DESC
            LIMIT ?
        """
        results = self.con.execute(pairs_query, [max_pairs])
        while batch := results.fetchmany(BATCH_SIZE):
            for left, right, score in batch:
                yield (Identifier.get(left), Identifier.get(right)), score

    def __repr__(self) -> str:
        return "<DuckDBIndex(%r, %r)>" % (
            self.view.scope.name,
            self.con,
        )
