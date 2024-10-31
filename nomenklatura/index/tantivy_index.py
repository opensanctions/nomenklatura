import logging
from pathlib import Path
from functools import lru_cache
from normality import WS, ascii_text
from followthemoney.types import registry
from typing import Any, Dict, List, Tuple, Generator, Set, Optional
from tantivy import Query, Occur, Index, SchemaBuilder, Document
from collections import defaultdict
from rigour.text import metaphone
from rigour.text.scripts import is_modern_alphabet

from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.resolver import Identifier, Pair
from nomenklatura.store import View
from nomenklatura.index.common import BaseIndex
from nomenklatura.util import clean_text_basic

log = logging.getLogger(__name__)

FIELD_ID = "entity_id"
FIELD_SCHEMA = "schemata"
FIELD_PHONETIC = "phonetic_name"
FIELD_TEXT = registry.text.name
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
    registry.text,
    registry.string,
    registry.address,
    registry.identifier,
    registry.phone,
    registry.email,
    registry.name,
}
BOOST_NAME_PHRASE = 4.0
BOOSTS = {
    registry.name.name: 5.0,
    # registry.phone.name: 5.0,
    # registry.email.name: 5.0,
    registry.address.name: 3.0,
    registry.identifier.name: 7.0,
}


@lru_cache(maxsize=20000)
def _ascii_word(word: str) -> Optional[str]:
    return ascii_text(word)


@lru_cache(maxsize=20000)
def _phonetic_word(word: str) -> Optional[str]:
    if not is_modern_alphabet(word) or len(word) < 3:
        return None
    phon = metaphone(_ascii_word(word))
    if len(phon) < 3:
        return None
    return phon


def _identifier_clean(value: str) -> Optional[str]:
    chars = [c for c in value if c.isalnum()]
    if len(chars) < 4:
        return None
    return "".join(chars).lower()


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
        schema_builder.add_text_field(FIELD_ID, tokenizer_name="raw", stored=True)
        schema_builder.add_text_field(FIELD_SCHEMA, tokenizer_name="raw")
        schema_builder.add_text_field(FIELD_TEXT)
        schema_builder.add_text_field(registry.name.name, tokenizer_name="raw")
        schema_builder.add_text_field(FIELD_PHONETIC, tokenizer_name="raw")
        # schema_builder.add_text_field(registry.email.name)
        schema_builder.add_text_field(registry.address.name)
        schema_builder.add_text_field(registry.identifier.name, tokenizer_name="raw")
        # schema_builder.add_text_field(registry.phone.name, tokenizer_name="raw")
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
    def index_entity(cls, entity: CE) -> Dict[str, Set[str]]:
        """Convert the given entity's properties into fields in a format suitable for indexing."""
        fields: Dict[str, Set[str]] = defaultdict(set)

        for prop, value in entity.itervalues():
            type = prop.type
            if type in INDEX_IGNORE or not prop.matchable:
                continue

            if type == registry.date:
                fields[type.name].add(value[:4])
                if len(value) > 9:
                    fields[type.name].add(value[:10])
                continue

            if type == registry.country:
                fields[type.name].add(value)
                continue

            cleaned = clean_text_basic(value)

            if type in FULL_TEXT and cleaned is not None:
                fields[FIELD_TEXT].add(cleaned)

            if type == registry.name and cleaned is not None:
                for word in cleaned.split(WS):
                    if not len(word):
                        continue
                    fields[type.name].add(word)
                    ascii = _ascii_word(word)
                    if ascii is not None:
                        fields[type.name].add(ascii)
                    phonetic = _phonetic_word(word)
                    if phonetic is not None:
                        fields[FIELD_PHONETIC].add(phonetic)
                continue

            if type == registry.identifier:
                clean_id = _identifier_clean(value)
                if clean_id is not None:
                    fields[type.name].add(clean_id)
                    fields[FIELD_TEXT].add(value)
                continue

            if type == registry.address and cleaned is not None:
                fields[type.name].add(cleaned)

        # print(dict(fields))
        return fields

    def field_queries(self, entity: CE) -> Generator[Query, None, None]:
        """
        A generator of queries for the given index field and set of values.
        """
        terms: Dict[str, Set[str]] = defaultdict(set)

        for prop, value in entity.itervalues():
            type = prop.type
            if type in INDEX_IGNORE or not prop.matchable:
                continue

            if type == registry.country:
                terms[type.name].add(value)
                continue

            if type == registry.date:
                terms[type.name].add(value[:4])
                if len(value) > 9:
                    terms[type.name].add(value[:10])
                continue

            cleaned = clean_text_basic(value)
            tokens = cleaned.split(WS) if cleaned else []
            tokens = [t for t in tokens if len(t) > 0]
            if type in FULL_TEXT:
                terms[FIELD_TEXT].update(tokens)

            if type == registry.identifier:
                clean_id = _identifier_clean(value)
                if clean_id is not None:
                    terms[type.name].add(clean_id)
                    terms[FIELD_TEXT].add(clean_id)
                continue

            if type == registry.name:
                for word in tokens:
                    terms[type.name].add(word)
                    phonetic = _phonetic_word(word)
                    if phonetic is not None:
                        terms[FIELD_PHONETIC].add(phonetic)
                    ascii_word = _ascii_word(word)
                    if ascii_word is not None:
                        terms[type.name].add(ascii_word)
                continue

            if type == registry.address:
                terms[type.name].update(tokens)
                continue

        for field, values in terms.items():
            if len(values) > 1:
                query = Query.term_set_query(self.schema, field, list(values))
            else:
                query = Query.term_query(self.schema, field, list(values)[0])
            if field in BOOSTS:
                query = Query.boost_query(query, BOOSTS[field])
            yield query

    def entity_query(self, entity: CE) -> Query:
        schema_query = Query.term_query(self.schema, FIELD_SCHEMA, entity.schema.name)
        queries: List[Tuple[Occur, Query]] = [(Occur.Must, schema_query)]
        if entity.id is not None:
            id_query = Query.term_query(self.schema, FIELD_ID, entity.id)
            queries.append((Occur.MustNot, id_query))
        for query in self.field_queries(entity):
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
            for field, values in self.index_entity(entity).items():
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
            if entity.id is None:
                continue
            if not entity.schema.matchable:
                continue
            if idx > 0 and idx % 10_000 == 0:
                log.info("Blocking pairs: %s (%s candidates)..." % (idx, candidates))
            idx += 1

            query = self.entity_query(entity)
            searcher = self.index.searcher()
            for score, address in searcher.search(query, self.max_candidates).hits:
                if score < threshold:
                    break
                # Value of type "Document" is not indexable
                doc = searcher.doc(address)
                other_id: str = doc["entity_id"][0]  # type: ignore
                if entity.id == other_id:
                    continue
                candidates += 1
                inverted = pairs.pop((other_id, entity.id), 0.0)
                score = max(score, inverted)
                pairs[(entity.id, other_id)] = score

                if len(pairs) > (max_pairs * 30):
                    _pairs = sorted(pairs.items(), key=lambda p: p[1], reverse=True)
                    _pairs = _pairs[:max_pairs]
                    threshold = _pairs[-1][1]
                    # print("Threshold:", threshold)
                    pairs = dict(_pairs)
        _pairs = sorted(pairs.items(), key=lambda p: p[1], reverse=True)
        _pairs = _pairs[:max_pairs]
        log.info("Blocked %s entities, picked from %s candidates." % (idx, candidates))
        return [(Identifier.pair(e, r), score) for (e, r), score in _pairs]
