from pathlib import Path
from typing import Dict, List, Tuple
from nomenklatura.index.common import BaseIndex
import logging
from functools import lru_cache
from tempfile import mkdtemp
import tantivy
from tantivy import Query, Occur
from followthemoney.types import registry

from nomenklatura.util import PathLike, fingerprint_name
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.index import BOOSTS
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer

log = logging.getLogger(__name__)
#handler = logging.StreamHandler(sys.stdout)
#handler.setLevel(logging.DEBUG)


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


class TantivyIndex(BaseIndex):
    def __init__(self, view: View[DS, CE]):
        super().__init__(view)
        self.tokenizer = Tokenizer[DS, CE]()
        self.path = Path(mkdtemp())
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("entity_id", tokenizer_name='raw', stored=True)
        schema_builder.add_text_field(registry.name.name)
        schema_builder.add_text_field(registry.email.name)
        schema_builder.add_text_field(registry.address.name)
        schema_builder.add_text_field(registry.identifier.name, tokenizer_name='raw')
        schema_builder.add_text_field(registry.phone.name, tokenizer_name='raw')
        schema_builder.add_text_field(registry.country.name, tokenizer_name='raw')
        schema_builder.add_text_field(registry.date.name, tokenizer_name='raw')
        schema_builder.add_text_field(NAME_PART_FIELD)
        schema_builder.add_text_field(WORD_FIELD)
        self.schema = schema_builder.build()
        self.index = tantivy.Index(self.schema, path=self.path.as_posix())

    def index_entity(self, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable or entity.id is None:
            return
        ident = Identifier.get(entity.id)
        document = tantivy.Document(entity_id=entity.id)
        for field, token in self.tokenizer.entity(entity):
            document.add_text(field, token)
        self.writer.add_document(document)

    def build(self) -> None:
        self.writer = self.index.writer()

        for entity in self.view.entities():
            self.index_entity(entity)
        self.commit()

    def commit(self) -> None:
        self.writer.commit()
        self.index.reload()
        self.searcher = self.index.searcher()
    
    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        queries = []
        for field, token in self.tokenizer.entity(entity):
            term_query = Query.term_query(self.schema, field, token)
            boost_query = Query.boost_query(term_query, BOOSTS.get(field, 1.0))
            queries.append((Occur.Should, boost_query))
        boolean_query = Query.boolean_query(queries)
        results = []
        for (score, address) in self.searcher.search(boolean_query, 10).hits:
            doc = self.searcher.doc(address)
            results.append((Identifier.get(doc["entity_id"][0]), score))
        return results
