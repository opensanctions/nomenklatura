import logging
from normality import WS
from pathlib import Path
from rigour.ids import StrictFormat
from followthemoney.types import registry
from typing import Any, Dict, List, Tuple, Generator, Set
from tantivy import Query, Occur, Index, SchemaBuilder, Document
import math
from collections import defaultdict

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Identifier, Pair
from nomenklatura.store import View
from nomenklatura.util import fingerprint_name, clean_text_basic
from nomenklatura.index.common import BaseIndex

log = logging.getLogger(__name__)

INDEX_IGNORE = (
    registry.entity,
    registry.url,
    registry.json,
    registry.html,
    registry.language,
    registry.mimetype,
    registry.checksum,
    # TODO: should topics be a field so that PEPs, sanctioned entities are more
    # easily found in xref?
    registry.topic,
)
FULL_TEXT = {
    # registry.text,
    registry.string,
    registry.address,
    registry.identifier,
    # registry.email,
}
BOOST_NAME_PHRASE = 4.0
BOOSTS = {
    registry.name.name: 4.0,
    registry.phone.name: 3.0,
    registry.email.name: 3.0,
    registry.address.name: 3.0,
    registry.identifier.name: 5.0,
}


class TantivyIndex(BaseIndex[DS, CE]):
    name = "tantivy"

    def __init__(
        self, view: View[DS, CE], data_dir: Path, options: Dict[str, Any] = {}
    ):
        self.view = view
        self.memory_budget = int(options.get("memory_budget", 500) * 1024 * 1024)
        self.max_candidates = int(options.get("max_candidates", 50))
        self.threshold = float(options.get("threshold", 1.0))

        schema_builder = SchemaBuilder()
        schema_builder.add_text_field("entity_id", tokenizer_name="raw", stored=True)
        schema_builder.add_text_field("schemata", tokenizer_name="raw")
        schema_builder.add_text_field(registry.name.name)
        schema_builder.add_text_field(registry.email.name)
        schema_builder.add_text_field(registry.address.name)
        schema_builder.add_text_field(registry.text.name)
        schema_builder.add_text_field(registry.identifier.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.iban.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.phone.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.country.name, tokenizer_name="raw")
        schema_builder.add_text_field(registry.date.name, tokenizer_name="raw")
        self.schema = schema_builder.build()

        self.index_dir = data_dir
        if self.index_dir.exists():
            self.index = Index.open(self.index_dir.as_posix())
            self.build_index = False
        else:
            self.index_dir.mkdir(parents=True)
            self.index = Index(self.schema, path=self.index_dir.as_posix())
            self.build_index = True

    @classmethod
    def entity_fields(cls, entity: CE) -> Generator[Tuple[str, Set[str]], None, None]:
        """
        A generator of each

        - index field name and
        -  the set of normalised but not tokenised values for that field

        for the given entity.
        """
        fields: Dict[str, Set[str]] = defaultdict(set)

        for prop, value in entity.itervalues():
            type = prop.type
            if type in INDEX_IGNORE:
                continue

            if type in FULL_TEXT:
                fields[registry.text.name].add(value.lower())

            if type == registry.name:
                fields[type.name].add(value.lower())
                norm = fingerprint_name(value)
                if norm is not None:
                    fields[type.name].add(norm)
                continue

            if type == registry.date and prop.matchable:
                if len(value) > 4:
                    fields[type.name].add(value[:4])
                fields[type.name].add(value[:10])
                continue

            if type == registry.identifier and prop.matchable:
                clean_id = StrictFormat.normalize(value)
                if clean_id is not None:
                    fields[type.name].add(clean_id)
                continue

            if type == registry.address and prop.matchable:
                cleaned = clean_text_basic(value)
                if cleaned is not None:
                    fields[type.name].add(cleaned)
                continue

            if prop.matchable and type in (
                registry.phone,
                registry.email,
                registry.country,
            ):
                fields[type.name].add(value)
        yield from fields.items()

    def field_queries(
        self, field: str, values: Set[str]
    ) -> Generator[Query, None, None]:
        """
        A generator of queries for the given index field and set of values.
        """
        # Name phrase
        if field == registry.name.name:
            for value in values:
                words = value.split(WS)
                word_count = len(words)
                if word_count > 1:
                    slop = math.ceil(2 * math.log(word_count))
                    yield Query.boost_query(
                        Query.phrase_query(self.schema, field, words, slop),  # type: ignore
                        BOOST_NAME_PHRASE,
                    )

        # Any of set of tokens in all values of the field
        if field in {
            registry.address.name,
            registry.name.name,
            registry.text.name,
            registry.string.name,
        }:
            word_set: Set[str] = set()
            for value in values:
                word_set.update(value.split(WS))
            term_queries: List[Query] = []
            for word in word_set:
                term_queries.append(Query.term_query(self.schema, field, word))
            yield Query.boost_query(
                Query.boolean_query([(Occur.Should, q) for q in term_queries]),
                BOOSTS.get(field, 1.0),
            )
            return

        # entire value as a term
        for value in values:
            yield Query.boost_query(
                Query.term_query(self.schema, field, value),
                BOOSTS.get(field, 1.0),
            )

    def entity_query(self, entity: CE) -> Query:
        schema_query = Query.term_query(self.schema, "schemata", entity.schema.name)
        queries: List[Tuple[Occur, Query]] = [(Occur.Must, schema_query)]
        if entity.id is not None:
            id_query = Query.term_query(self.schema, "entity_id", entity.id)
            queries.append((Occur.MustNot, id_query))
        for field, value in self.entity_fields(entity):
            for query in self.field_queries(field, value):
                queries.append((Occur.Should, query))
        return Query.boolean_query(queries)

    def build(self) -> None:
        if not self.build_index:
            log.info("Using existing index at %s", self.index_dir)
            return

        log.info("Building index from: %r...", self.view)
        writer = self.index.writer(self.memory_budget)
        writer.delete_all_documents()
        idx = 0
        for entity in self.view.entities():
            if not entity.schema.matchable or entity.id is None:
                continue
            if idx > 0 and idx % 50_000 == 0:
                log.info("Indexing entity: %s..." % idx)
            idx += 1
            schemata = [s.name for s in entity.schema.matchable_schemata]
            document = Document(entity_id=entity.id, schemata=schemata)
            for field, values in self.entity_fields(entity):
                for value in values:
                    document.add_text(field, value)
            writer.add_document(document)
        writer.commit()
        self.index.reload()
        log.info("Index is built (%s matchable entities)." % idx)

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

    def pairs(self, max_pairs: int = BaseIndex.MAX_PAIRS) -> List[Tuple[Pair, float]]:
        """
        Compare all matchable entities in the index and return pairs in order of
        similarity.
        """
        pairs: Dict[Tuple[str, str], float] = {}
        threshold = float(self.threshold)

        idx = 0
        candidates = 0
        for entity in self.view.entities():
            if not entity.schema.matchable or entity.id is None:
                continue
            if idx > 0 and idx % 10_000 == 0:
                log.info("Blocking pairs: %s (%s candidates)..." % (idx, candidates))
            idx += 1

            query = self.entity_query(entity)
            searcher = self.index.searcher()
            for score, address in searcher.search(query, self.max_candidates).hits:
                candidates += 1
                if score < threshold:
                    break
                # Value of type "Document" is not indexable
                doc = searcher.doc(address)
                other_id: str = doc["entity_id"][0]  # type: ignore
                if entity.id == other_id:
                    continue
                if (other_id, entity.id) in pairs:
                    score = max(score, pairs.pop((other_id, entity.id)))
                pairs[(entity.id, other_id)] = score

                if len(pairs) > (max_pairs * 5):
                    _pairs = sorted(pairs.items(), key=lambda p: p[1], reverse=True)
                    _pairs = _pairs[:max_pairs]
                    threshold = _pairs[-1][1]
                    # print("Threshold:", threshold)
                    pairs = dict(_pairs)
        _pairs = sorted(pairs.items(), key=lambda p: p[1], reverse=True)
        _pairs = _pairs[:max_pairs]
        log.info("Blocked %s entities, picked from %s candidates." % (idx, candidates))
        return [(Identifier.pair(e, r), score) for (e, r), score in _pairs]
