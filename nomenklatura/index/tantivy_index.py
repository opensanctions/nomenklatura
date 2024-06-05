from followthemoney.property import Property
from followthemoney.types import registry
from normality import WS
from pathlib import Path
from rigour.ids import StrictFormat
from tantivy import Query, Occur
from typing import Any, Dict, List, Tuple, Generator
import logging
import tantivy

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, SKIP_FULL, TEXT_TYPES
from nomenklatura.resolver import Identifier
from nomenklatura.store import View
from nomenklatura.util import name_words, clean_text_basic, fingerprint_name

log = logging.getLogger(__name__)

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
    registry.address.name: 2.5,
    registry.identifier.name: 3.0,
}


class Tokenizer():
    def value(
        self, prop: Property, value: str
    ) -> Generator[Tuple[str, str], None, None]:
        """Perform type-specific token generation for a property value."""
        type = prop.type
        if not prop.matchable:
            return
        if type in (registry.url, registry.topic, registry.entity):
            return
        if type not in SKIP_FULL:
            token_value = value[:100].lower()
            yield type.name, token_value
        if type == registry.date:
            if len(value) > 4:
                yield type.name, value[:4]
            yield type.name, value[:10]
            return
        if type == registry.name:
            norm = fingerprint_name(value)
            if norm is not None:
                yield type.name, norm
                for token in norm.split(WS):
                    if len(token) > 2 and len(token) < 30:
                        yield NAME_PART_FIELD, token
            return
        if type == registry.identifier:
            clean_id = StrictFormat.normalize(value)
            if clean_id is not None:
                yield type.name, clean_id
            return
        if type in TEXT_TYPES:
            for word in name_words(clean_text_basic(value), min_length=3):
                yield WORD_FIELD, word

    def entity(self, entity: CE) -> Generator[Tuple[str, str], None, None]:
        for prop, value in entity.itervalues():
            for field, token in self.value(prop, value):
                yield field, token


class TantivyIndex():
    def __init__(
        self, view: View[DS, CE], data_dir: Path, options: Dict[str, Any] = {}
    ):
        self.view = view
        self.tokenizer = Tokenizer()
        self.memory_budget = int(options.get("memory_budget", 1024) * 1024 * 1024)
        self.max_candidates = int(options.get("max_candidates", 100))

        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("entity_id", tokenizer_name="raw", stored=True)
        schema_builder.add_text_field(registry.name.name)
        schema_builder.add_text_field(registry.email.name)
        schema_builder.add_text_field(registry.address.name)
        schema_builder.add_text_field(registry.identifier.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.iban.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.phone.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.country.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.date.name, tokenizer_name="raw")
        schema_builder.add_text_field(NAME_PART_FIELD)
        schema_builder.add_text_field(WORD_FIELD)
        self.schema = schema_builder.build()

        self.index_dir = data_dir / "tantivy-index"
        if self.index_dir.exists():
            self.exists = True
            self.index = tantivy.Index.open(self.index_dir.as_posix())
        else:
            self.exists = False
            self.index_dir.mkdir(parents=True)
            self.index = tantivy.Index(self.schema, path=self.index_dir.as_posix())
            self.index_writer = self.index.writer(self.memory_budget)

    def index_entity(self, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable or entity.id is None:
            return
        document = tantivy.Document(entity_id=entity.id)
        for field, token in self.tokenizer.entity(entity):
            document.add_text(field, token)
        self.index_writer.add_document(document)

    def build(self) -> None:
        if self.exists:
            log.info("Using existing index at %s", self.index_dir)
        else:
            log.info("Building index from: %r...", self.view)

            for entity in self.view.entities():
                self.index_entity(entity)

            self.index_writer.commit()
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
        for score, address in self.searcher.search(
            boolean_query, self.max_candidates
        ).hits:
            doc = self.searcher.doc(address)
            # Value of type "Document" is not indexable
            results.append((Identifier.get(doc["entity_id"][0]), score))  # type: ignore
        return results
