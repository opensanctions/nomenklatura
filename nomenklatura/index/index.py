import pickle
import logging
import statistics
from collections import defaultdict
from typing import Any, Dict, Generator, Generic, Tuple, cast
from followthemoney.schema import Schema

from nomenklatura.util import PathLike
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
                self.inverted[token] = IndexEntry(self, token)
            self.inverted[token].add(entity.id, weight=weight)
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
        log.info("Building index from: %r...", self.loader)
        self.inverted = {}
        self.terms = {}
        for entity in self.loader:
            self.index(entity, adjacent=adjacent)
        self.commit()
        log.info("Built index: %r", self)

    def commit(self) -> None:
        quantiles = statistics.quantiles(self.terms.values(), n=3)
        min_terms = float(quantiles[0])

        for entry in self.inverted.values():
            entry.compute(min_terms)

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

        tokens: Dict[str, float] = defaultdict(float)
        for token, _ in self.tokenizer.entity(query):
            tokens[token] += 1

        matches: Dict[str, float] = defaultdict(float)
        for token, _ in tokens.items():
            entry = self.inverted.get(token)
            if entry is None or entry.idf is None:
                continue
            for entity_id, tf in entry.frequencies.items():
                matches[entity_id] += tf * entry.idf

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
            entity = self.loader.get_entity(result_id)
            if entity is not None:
                returned += 1
                yield entity, score
            if returned >= limit:
                break

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
