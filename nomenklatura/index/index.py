from pathlib import Path
import pickle
import logging
from itertools import combinations
from collections import defaultdict
from typing import Any, Dict, Generator, Generic, List, Optional, Set, Tuple, cast
from followthemoney.schema import Schema
from followthemoney.types import registry

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.loader import Loader
from nomenklatura.index.entry import Field
from nomenklatura.index.tokenizer import (
    NGRAM_FIELD,
    SCHEMA_FIELD,
    WORD_FIELD,
    Tokenizer,
)

log = logging.getLogger(__name__)


class Index(Generic[DS, CE]):
    """An in-memory search index to match entities against a given dataset."""

    BOOSTS = {
        SCHEMA_FIELD: 0.0,
        NGRAM_FIELD: 0.2,
        WORD_FIELD: 0.5,
        registry.name.name: 10.0,
        # registry.country.name: 1.5,
        # registry.date.name: 1.5,
        # registry.language: 0.7,
        registry.iban.name: 3.0,
        registry.phone.name: 3.0,
        registry.email.name: 3.0,
        # registry.entity: 0.0,
        # registry.topic: 2.1,
        # registry.address.name: 2.5,
        registry.identifier.name: 3.0,
    }

    __slots__ = "loader", "fields", "tokenizer", "entities"

    def __init__(self, loader: Loader[DS, CE]):
        self.loader = loader
        self.tokenizer = Tokenizer[DS, CE]()
        self.fields: Dict[str, Field] = {}
        self.entities: Set[str] = set()

    def index(self, entity: CE, adjacent: bool = True) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable:
            return
        loader = self.loader if adjacent else None
        for field, token in self.tokenizer.entity(entity, loader=loader):
            if field not in self.fields:
                self.fields[field] = Field()
            self.fields[field].add(entity.id, token)
        self.entities.add(entity.id)

    def build(self, adjacent: bool = True) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.loader)
        self.fields = {}
        self.entities = set()
        for entity in self.loader:
            self.index(entity, adjacent=adjacent)
        self.commit()
        log.info("Built index: %r", self)

    def commit(self) -> None:
        for field in self.fields.values():
            field.compute()

    def _match_schema(self, entity_id: str, schema: Schema) -> bool:
        tokens: Set[str] = set()
        for matchable in schema.matchable_schemata:
            tokens.add(self.tokenizer.schema_token(matchable))
        for parent in schema.descendants:
            tokens.add(self.tokenizer.schema_token(parent))
        field = self.fields.get(SCHEMA_FIELD)
        if field is None:
            return False
        for token in tokens:
            entry = field.tokens.get(token)
            if entry is None:
                continue
            if entity_id in entry.entities:
                return True
        return False

    def match(
        self, query: CE, limit: Optional[int] = 30
    ) -> Generator[Tuple[str, float], None, None]:
        """Find entities similar to the given input entity, return ID."""

        matches: Dict[str, float] = defaultdict(float)
        for field_, token in self.tokenizer.entity(query):
            try:
                field = self.fields[field_]
            except KeyError:
                continue
            entry = field.tokens.get(token)
            if entry is None or entry.idf is None:
                continue
            for entity_id, tf in entry.frequencies(field):
                score = (tf * entry.idf) * self.BOOSTS.get(field_, 1.0)
                matches[entity_id] += score

        results = sorted(matches.items(), key=lambda x: x[1], reverse=True)
        log.debug("Match entity: %r (%d results)", query, len(results))
        returned = 0
        for result_id, score in results:
            if score <= 0.0:
                break
            if result_id == query.id:
                continue
            if not self._match_schema(result_id, query.schema):
                continue

            yield result_id, score
            returned += 1
            if limit is not None and returned >= limit:
                break

    def match_entities(
        self, query: CE, limit: int = 30
    ) -> Generator[Tuple[CE, float], None, None]:
        """Find entities similar to the given input entity, return entity."""
        returned = 0
        for entity_id, score in self.match(query, limit=None):
            entity = self.loader.get_entity(entity_id)
            if entity is not None:
                yield entity, score
                returned += 1

            if returned >= limit:
                break

    def pairs(self) -> List[Tuple[Pair, float]]:
        """A second method of doing xref: summing up the pairwise match value
        for all entities lineraly. This uses a lot of memory but is really
        fast."""
        pairs: Dict[Pair, float] = {}
        log.info("Building index blocking pairs...")
        for field_name, field in self.fields.items():
            # if field_name in (SCHEMA_FIELD, NGRAM_FIELD, WORD_FIELD):
            # if field_name in (SCHEMA_FIELD, NGRAM_FIELD):
            if field_name == SCHEMA_FIELD:
                continue
            boost = self.BOOSTS.get(field_name, 1.0)
            for idx, entry in enumerate(field.tokens.values()):
                if idx % 10000 == 0:
                    log.info("Pairwise xref [%s]: %d" % (field_name, idx))

                if len(entry.entities) == 1 or len(entry.entities) > 100:
                    continue
                entities = sorted(
                    entry.frequencies(field), key=lambda f: f[1], reverse=True
                )
                for (left, lw), (right, rw) in combinations(entities, 2):
                    if lw == 0.0 or rw == 0.0:
                        continue
                    pair = Identifier.pair(left, right)
                    if pair not in pairs:
                        pairs[pair] = 0
                    score = (lw + rw) * boost
                    pairs[pair] += score

        return sorted(pairs.items(), key=lambda p: p[1], reverse=True)

    def save(self, path: PathLike) -> None:
        with open(path, "wb") as fh:
            pickle.dump(self.to_dict(), fh)

    @classmethod
    def load(cls, loader: Loader[DS, CE], path: Path) -> "Index[DS, CE]":
        index = Index(loader)
        if not path.exists():
            log.debug("Cannot load: %r", index)
            index.build()
            index.save(path)
            return index

        with open(path, "rb") as fh:
            state = pickle.load(fh)
            index.from_dict(state)
            index.commit()
        log.debug("Loaded: %r", index)
        return index

    def to_dict(self) -> Dict[str, Any]:
        """Prepare an index for pickling."""
        return {
            "fields": {n: f.to_dict() for n, f in self.fields.items()},
            "entities": self.entities,
        }

    def from_dict(self, state: Dict[str, Any]) -> None:
        """Restore a pickled index."""
        fields = state["fields"].items()
        self.fields = {t: Field.from_dict(i) for t, i in fields}
        self.entities = set(cast(Set[str], state.get("entities")))

    def __len__(self) -> int:
        return len(self.entities)

    def __repr__(self) -> str:
        return "<Index(%r, %d, %d)>" % (
            self.loader.dataset.name,
            len(self.fields),
            len(self.entities),
        )
