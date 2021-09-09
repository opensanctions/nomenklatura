import math
import pickle
import logging
from typing import Any, Dict, Generator, Generic, Tuple, cast
from normality import normalize, WS
from followthemoney.schema import Schema
from followthemoney.types import registry
from followthemoney.types.common import PropertyType

from nomenklatura.util import PathLike
from nomenklatura.index.util import ngrams
from nomenklatura.loader import DS, E, Loader
from nomenklatura.index.entry import IndexEntry
from nomenklatura.index.tokenizer import Tokenizer

log = logging.getLogger(__name__)


class Index(Generic[DS, E]):
    """An in-memory search index to match entities against a given dataset."""

    def __init__(self, loader: Loader[DS, E]):
        self.loader = loader
        self.inverted: Dict[str, IndexEntry[DS, E]] = {}
        self.tokenizer = Tokenizer[DS, E]()
        self.terms: Dict[str, int] = {}

    def index(self, entity: E, adjacent: bool = True) -> None:
        """Index one entity. This is not idempodent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable:
            return
        terms = 0
        loader = self.loader if adjacent else None
        for token, weight in self.tokenizer.entity(entity, loader=loader):
            if token not in self.inverted:
                self.inverted[token] = IndexEntry(self, token, weight=weight)
            self.inverted[token].add(entity.id)
            terms += 1
        self.terms[entity.id] = terms
        log.debug("Index entity: %r (%d terms)", entity, terms)

    # def remove(self, entity):
    #     """Remove an entity from the index."""
    #     self.terms.pop(entity.id, None)
    #     for entry in self.inverted.values():
    #         entry.remove(entity.id)

    def build(self, adjacent: bool = True) -> None:
        """Index all entities in the dataset."""
        self.inverted = {}
        self.terms = {}
        for entity in self.loader:
            self.index(entity, adjacent=adjacent)
        self.commit()
        log.info("Built index: %r", self)

    def commit(self) -> None:
        for entry in self.inverted.values():
            entry.compute()

    def _match_schema(self, entity_id: str, schema: Schema) -> bool:
        tokens = set()
        for matchable in schema.matchable_schemata:
            tokens.add(self.tokenizer.schema_token(matchable))
        for token in tokens:
            entry = self.inverted.get(token)
            if entry is not None and entity_id in entry.entities:
                return True
        return False

    def match(
        self, query: E, limit: int = 30
    ) -> Generator[Tuple[E, float], None, None]:
        """Find entities similar to the given input entity."""
        if not query.schema.matchable:
            return
        invalid = -1.0
        matches: Dict[str, float] = {}
        for token, _ in self.tokenizer.entity(query):
            entry = self.inverted.get(token)
            if entry is None or len(entry) == 0:
                continue
            idf = math.log(len(self) / len(entry))
            for entity_id, tf in entry.all_tf():
                if entity_id == query.id or tf <= 0:
                    continue

                weight = tf * idf
                entity_score = matches.get(entity_id)
                if entity_score == invalid:
                    continue
                if entity_score is None:
                    # Filter out incompatible types:
                    if not self._match_schema(entity_id, query.schema):
                        matches[entity_id] = invalid
                        continue
                    entity_score = 0
                matches[entity_id] = entity_score + weight

        results = sorted(matches.items(), key=lambda x: x[1], reverse=True)
        results = [(id, score) for (id, score) in results if score > 0]
        log.debug("Match entity: %r (%d results)", query, len(results))
        for result_id, score in results[:limit]:
            entity = self.loader.get_entity(result_id)
            if entity is not None:
                yield entity, score

    def save(self, path: PathLike) -> None:
        with open(path, "wb") as fh:
            pickle.dump(self.to_dict(), fh)

    @classmethod
    def load(cls, loader: Loader[DS, E], path: PathLike) -> "Index[DS, E]":
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
            "dataset": self.loader.dataset.name,
            "inverted": [t.to_dict() for t in self.inverted.values()],
            "terms": self.terms,
        }

    def from_dict(self, state: Dict[str, Any]) -> None:
        """Restore a pickled index."""
        entries = [IndexEntry.from_dict(self, i) for i in state["inverted"]]
        self.inverted = {e.token: e for e in entries}
        self.terms = cast(Dict[str, int], state.get("terms"))

    def __len__(self) -> int:
        return len(self.terms)

    def __repr__(self) -> str:
        return "<Index(%r, %d, %d)>" % (
            self.loader.dataset.name,
            len(self.inverted),
            len(self.terms),
        )
