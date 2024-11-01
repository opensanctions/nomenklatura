import csv
from pathlib import Path
import logging
from itertools import combinations
from tempfile import mkdtemp
from typing import Any, Dict, List, Set, Tuple
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
        log.info("Index built.")
        
    def frequencies(self, field: str, token: str) -> List[Tuple[str, float]]:
        """
        """

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
