import pickle
import logging
import statistics
from itertools import combinations
from collections import defaultdict
from typing import Any, Dict, Generator, Generic, List, Optional, Tuple, cast
from followthemoney.schema import Schema

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.entity import DS, E
from nomenklatura.loader import Loader
from nomenklatura.index.entry import IndexEntry
from nomenklatura.index.tokenizer import Tokenizer

log = logging.getLogger(__name__)


class Index(Generic[DS, E]):
    """An in-memory search index to match entities against a given dataset."""

    __slots__ = "loader", "inverted", "tokenizer", "terms", "min_terms"

    def __init__(self, loader: Loader[DS, E]):
        self.loader = loader
        self.tokenizer = Tokenizer[DS, E]()
        self.inverted: Dict[str, IndexEntry[DS, E]] = {}
        self.terms: Dict[str, float] = {}

    def index(self, entity: E, adjacent: bool = True, fuzzy: bool = True) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable:
            return
        terms = 0.0
        loader = self.loader if adjacent else None
        for token, weight in self.tokenizer.entity(entity, loader=loader, fuzzy=fuzzy):
            if token not in self.inverted:
                self.inverted[token] = IndexEntry()
            self.inverted[token].add(entity.id, weight=weight)
            terms += weight
        self.terms[entity.id] = terms
        log.debug("Index entity: %r (%d terms)", entity, terms)

    def build(self, adjacent: bool = True, fuzzy: bool = True) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.loader)
        self.inverted = {}
        self.terms = {}
        for entity in self.loader:
            self.index(entity, adjacent=adjacent, fuzzy=fuzzy)
        self.commit()
        log.info("Built index: %r", self)

    def commit(self) -> None:
        quantiles = statistics.quantiles(self.terms.values(), n=3)
        self.min_terms = float(quantiles[0])

        for entry in self.inverted.values():
            entry.compute(self)

    def _match_schema(self, entity_id: str, schema: Schema) -> bool:
        tokens = set()
        for matchable in schema.matchable_schemata:
            tokens.add(self.tokenizer.schema_token(matchable))
        for parent in schema.descendants:
            tokens.add(self.tokenizer.schema_token(parent))
        for token in tokens:
            entry = self.inverted.get(token)
            if entry is not None and entity_id in entry.entities:
                return True
        return False

    def match(
        self, query: E, limit: Optional[int] = 30, fuzzy: bool = True
    ) -> Generator[Tuple[str, float], None, None]:
        """Find entities similar to the given input entity, return ID."""
        tokens: Dict[str, float] = defaultdict(float)
        for token, _ in self.tokenizer.entity(query, fuzzy=fuzzy):
            tokens[token] += 1

        matches: Dict[str, float] = defaultdict(float)
        for token, _ in tokens.items():
            entry = self.inverted.get(token)
            if entry is None or entry.idf is None:
                continue
            for entity_id, tf in entry.frequencies(self):
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

            yield result_id, score
            returned += 1
            if limit is not None and returned >= limit:
                break

    def match_entities(
        self, query: E, limit: int = 30, fuzzy: bool = True
    ) -> Generator[Tuple[E, float], None, None]:
        """Find entities similar to the given input entity, return entity."""
        returned = 0
        for entity_id, score in self.match(query, limit=None, fuzzy=fuzzy):
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
        total = len(self.inverted)
        log.info("Building index blocking pairs (%d)..." % total)
        for idx, entry in enumerate(self.inverted.values()):
            if idx % 1000 == 0:
                log.info("Pairwise xref: %d/%d" % (idx, total))

            frequencies = list(entry.frequencies(self))
            if len(frequencies) == 1:
                continue
            entities = sorted(frequencies, key=lambda f: f[1], reverse=True)
            entities = entities[:200]
            for (left, lw), (right, rw) in combinations(entities, 2):
                if lw == 0.0 or rw == 0.0:
                    continue
                pair = Identifier.pair(left, right)
                if pair not in pairs:
                    pairs[pair] = 0
                score = lw + rw
                pairs[pair] += score

        return sorted(pairs.items(), key=lambda p: p[1], reverse=True)

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
            "inverted": {t: e.to_dict() for t, e in self.inverted.items()},
            "terms": self.terms,
        }

    def from_dict(self, state: Dict[str, Any]) -> None:
        """Restore a pickled index."""
        inverted = state["inverted"].items()
        self.inverted = {t: IndexEntry.from_dict(i) for t, i in inverted}
        self.terms = cast(Dict[str, float], state.get("terms"))

    def __len__(self) -> int:
        return len(self.terms)

    def __repr__(self) -> str:
        return "<Index(%r, %d, %d)>" % (
            self.loader.dataset.name,
            len(self.inverted),
            len(self.terms),
        )
