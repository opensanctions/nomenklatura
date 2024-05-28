from pathlib import Path
from typing import Dict, Generator, List, Tuple
from nomenklatura.index.common import BaseIndex
from nomenklatura.index.index import Index
import duckdb
import logging
import csv
from functools import lru_cache
from tempfile import mkdtemp
import tantivy

from nomenklatura.util import PathLike, fingerprint_name
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.index import BOOSTS
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer

log = logging.getLogger(__name__)


class TantivyIndex(BaseIndex):
    def __init__(self, view: View[DS, CE]):
        super().__init__(view)
        self.path = Path(mkdtemp())
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("entity_id", tokenizer_name='raw', stored=True)
        # TODO: The rest of the fields
        schema_builder.add_text_field("name", stored=True)
        self.schema = schema_builder.build()
        self.index = tantivy.Index(self.schema, path=self.path.as_posix())

    def build(self) -> None:
        writer = self.index.writer()

        for entity in self.view.entities():
            if not entity.schema.matchable:
                continue
            names = [fingerprint_name(n) for n in entity.get("name")]
            names = [n for n in names if n is not None]
            if names:
                writer.add_document(tantivy.Document(entity_id=entity.id, name=names))
        writer.commit()
        self.index.reload()
        self.searcher = self.index.searcher()
    
    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        names = [fingerprint_name(n) for n in entity.get("name")]
        names = [n for n in names if n is not None]
        name = " ".join(names)
        if not name:
            return []
        query = self.index.parse_query(name, ["name"])
        results = []
        for (score, address) in self.searcher.search(query, 10).hits:
            doc = self.searcher.doc(address)
            results.append((Identifier.get(doc["entity_id"][0]), score))
        return results
