from followthemoney.types import registry
from pathlib import Path
from tantivy import Query, Occur
from typing import Any, Dict, List, Tuple, Generic
import logging
import shutil
import tantivy

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer
from nomenklatura.resolver import Identifier
from nomenklatura.store import View

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
    # registry.entity: 0.0,
    # registry.topic: 2.1,
    registry.address.name: 2.5,
    registry.identifier.name: 3.0,
}


class TantivyIndex(Generic[DS, CE]):
    def __init__(
        self, view: View[DS, CE], data_dir: Path, options: Dict[str, Any] = {}
    ):
        self.view = view
        self.tokenizer = Tokenizer[DS, CE]()
        self.memory_budget = int(options.get("memory_budget", 1024) * 1024 * 1024)
        self.max_candidates = int(options.get("max_candidates", 100))

        self.data_dir = data_dir / "tantivy-index"
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)
        self.data_dir.mkdir(parents=True)

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
        self.index = tantivy.Index(self.schema, path=self.data_dir.as_posix())
        self.indexed_fields = set()

    def index_entity(self, writer, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable or entity.id is None:
            return
        document = tantivy.Document(entity_id=entity.id)
        for field, token in self.tokenizer.entity(entity):
            document.add_text(field, token)
            self.indexed_fields.add(field)
        writer.add_document(document)

    def build(self) -> None:
        log.info(
            "Building index from: %r... (memory budget %d bytes)",
            self.view,
            self.memory_budget,
        )
        writer = self.index.writer(self.memory_budget)

        for entity in self.view.entities():
            self.index_entity(writer, entity)

        writer.commit()
        self.index.reload()
        self.searcher = self.index.searcher()

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        queries = []
        for field, token in self.tokenizer.entity(entity):
            if field not in self.indexed_fields:
                continue
            term_query = Query.term_query(self.schema, field, token)
            boost_query = Query.boost_query(term_query, BOOSTS.get(field, 1.0))
            queries.append((Occur.Should, boost_query))
        boolean_query = Query.boolean_query(queries)
        results = []
        for score, address in self.searcher.search(
            boolean_query, self.max_candidates
        ).hits:
            doc = self.searcher.doc(address)
            results.append((Identifier.get(doc["entity_id"][0]), score))
        return results
