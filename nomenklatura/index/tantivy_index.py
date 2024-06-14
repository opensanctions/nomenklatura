import logging
from followthemoney.types import registry
from normality import WS
from pathlib import Path
from rigour.ids import StrictFormat
from tantivy import Query, Occur, Index, SchemaBuilder, Document
from typing import Any, Dict, List, Tuple, Generator
from collections import defaultdict

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Identifier, Pair
from nomenklatura.store import View
from nomenklatura.util import clean_text_basic, fingerprint_name
from nomenklatura.index.common import BaseIndex

log = logging.getLogger(__name__)

SKIP_FULL = (registry.address,)

BOOSTS = {
    registry.name.name: 10.0,
    registry.phone.name: 3.0,
    registry.email.name: 3.0,
    registry.address.name: 2.5,
    registry.identifier.name: 3.0,
}


class TantivyIndex(BaseIndex[DS, CE]):
    name = "tantivy"

    def __init__(
        self, view: View[DS, CE], data_dir: Path, options: Dict[str, Any] = {}
    ):
        self.view = view
        self.memory_budget = int(options.get("memory_budget", 100) * 1024 * 1024)
        self.max_candidates = int(options.get("max_candidates", 100))
        self.threshold = float(options.get("threshold", 1.0))

        schema_builder = SchemaBuilder()
        schema_builder.add_text_field("entity_id", tokenizer_name="raw", stored=True)
        schema_builder.add_text_field(registry.name.name)
        schema_builder.add_text_field(registry.email.name)
        schema_builder.add_text_field(registry.address.name)
        schema_builder.add_text_field(registry.identifier.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.iban.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.phone.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.country.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.date.name, tokenizer_name="raw")
        self.schema = schema_builder.build()

        self.index_dir = data_dir
        if self.index_dir.exists():
            self.index = Index.open(self.index_dir.as_posix())
        else:
            self.index_dir.mkdir(parents=True)
            self.index = Index(self.schema, path=self.index_dir.as_posix())

    @classmethod
    def entity_fields(cls, entity: CE) -> Generator[Tuple[str, str], None, None]:
        for prop, value in entity.itervalues():
            type = prop.type

            if not prop.matchable:
                continue

            if type in {registry.entity, registry.url}:
                continue

            if type == registry.date:
                if len(value) > 4:
                    yield type.name, value[:4]
                yield type.name, value[:10]
                continue

            if type == registry.name:
                norm = fingerprint_name(value)
                if norm is not None:
                    yield type.name, norm
                continue

            if type == registry.identifier:
                clean_id = StrictFormat.normalize(value)
                if clean_id is not None:
                    yield type.name, clean_id
                continue

            length_limited = clean_text_basic(value[:100])
            if length_limited is not None:
                yield type.name, length_limited

    def field_queries(self, field: str, value: str) -> Generator[Query, None, None]:
        words = value.split(WS)
        if field == registry.name.name:
            if len(words) > 2:
                slop = 1
                # Argument 3 to "phrase_query" of "Query" has incompatible
                # type "list[str]"; expected "list[str | tuple[int, str]]"
                yield Query.phrase_query(self.schema, field, words, slop)  # type: ignore

        if field in {registry.address.name, registry.name.name}:
            # TermSetQuery doesn't seem to behave so just use multiple term queries
            # as the parser does.
            for word in words:
                yield Query.term_query(self.schema, field, word)
            return

        yield Query.term_query(self.schema, field, value)

    def entity_query(self, entity: CE) -> Query:
        queries = []
        for field, value in TantivyIndex.entity_fields(entity):
            for query in self.field_queries(field, value):
                boost_query = Query.boost_query(query, BOOSTS.get(field, 1.0))
                queries.append((Occur.Should, boost_query))
        return Query.boolean_query(queries)

    def build(self) -> None:
        log.info("Building index from: %r...", self.view)
        writer = self.index.writer(self.memory_budget)
        writer.delete_all_documents()
        for idx, entity in enumerate(self.view.entities()):
            if not entity.schema.matchable or entity.id is None:
                continue
            if idx > 0 and idx % 50_000 == 0:
                log.info("Indexing entity: %s..." % idx)
            document = Document(entity_id=entity.id)
            for field, value in self.entity_fields(entity):
                document.add_text(field, value)
            writer.add_document(document)
        writer.commit()
        self.index.reload()
        log.info("Index is built.")

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        query = self.entity_query(entity)
        results = []
        searcher = self.index.searcher()
        for score, address in searcher.search(query, self.max_candidates).hits:
            if score < self.threshold:
                break
            doc = searcher.doc(address)
            # Value of type "Document" is not indexable
            results.append((Identifier.get(doc["entity_id"][0]), score))  # type: ignore
        return results

    def pairs(self) -> List[Tuple[Pair, float]]:
        """
        Compare all matchable entities in the index and return pairs in order of
        similarity.
        """
        pairs: Dict[Pair, float] = defaultdict(lambda: 1.0)

        for entity in self.view.entities():
            if not entity.schema.matchable or entity.id is None:
                continue

            query = self.entity_query(entity)
            ident = Identifier(entity.id)
            searcher = self.index.searcher()
            for score, address in searcher.search(query, self.max_candidates).hits:
                if score < self.threshold:
                    break
                # Value of type "Document" is not indexable
                doc = searcher.doc(address)
                other_ident = Identifier(doc["entity_id"][0])  # type: ignore
                if ident == other_ident:
                    continue
                pair = (max(ident, other_ident), min(ident, other_ident))
                pairs[pair] *= score
        return sorted(pairs.items(), key=lambda p: p[1], reverse=True)
