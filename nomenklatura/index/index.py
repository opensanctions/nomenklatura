from pathlib import Path
import pickle
import logging
from itertools import combinations
from typing import Any, Dict, List, Set, Tuple
from followthemoney.types import registry

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer
from nomenklatura.index.common import BaseIndex

log = logging.getLogger(__name__)


class Index(BaseIndex[DS, CE]):
    """An in-memory search index to match entities against a given dataset."""

    name = "memory"

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

    __slots__ = "view", "fields", "tokenizer", "entities"

    def __init__(self, view: View[DS, CE], data_dir: Path):
        self.view = view
        self.tokenizer = Tokenizer[DS, CE]()
        self.fields: Dict[str, Field] = {}
        self.entities: Set[Identifier] = set()

    def index(self, entity: CE) -> None:
        """Index one entity. This is not idempotent, you need to remove the
        entity before re-indexing it."""
        if not entity.schema.matchable or entity.id is None:
            return
        ident = Identifier.get(entity.id)
        for field, token in self.tokenizer.entity(entity):
            if field not in self.fields:
                self.fields[field] = Field()
            self.fields[field].add(ident, token)
        self.entities.add(ident)

    def build(self) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.view)
        self.fields = {}
        self.entities = set()
        for entity in self.view.entities():
            self.index(entity)
        self.commit()
        log.info("Built index: %r", self)

    def commit(self) -> None:
        for field in self.fields.values():
            field.compute()

    def pairs(self, max_pairs: int = BaseIndex.MAX_PAIRS) -> List[Tuple[Pair, float]]:
        """A second method of doing xref: summing up the pairwise match value
        for all entities lineraly. This uses a lot of memory but is really
        fast."""
        pairs: Dict[Pair, float] = {}
        log.info("Building index blocking pairs...")
        for field_name, field in self.fields.items():
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
                    pair = (max(left, right), min(left, right))
                    if pair not in pairs:
                        pairs[pair] = 0
                    score = (lw + rw) * boost
                    pairs[pair] += score

        return sorted(pairs.items(), key=lambda p: p[1], reverse=True)[:max_pairs]

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        """Match an entity against the index, returning a list of
        (entity_id, score) pairs."""
        scores: Dict[Identifier, float] = {}
        for field_name, token in self.tokenizer.entity(entity):
            field = self.fields.get(field_name)
            if field is None:
                continue
            entry = field.tokens.get(token)
            if entry is None:
                continue
            for ident, weight in entry.frequencies(field):
                if ident not in scores:
                    scores[ident] = 0.0
                scores[ident] += weight * self.BOOSTS.get(field_name, 1.0)
        return sorted(scores.items(), key=lambda s: s[1], reverse=True)

    def save(self, path: PathLike) -> None:
        with open(path, "wb") as fh:
            pickle.dump(self.to_dict(), fh)

    @classmethod
    def load(cls, view: View[DS, CE], path: Path, data_dir: Path) -> "Index[DS, CE]":
        index = Index(view, data_dir)
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
            "entities": [e.id for e in self.entities],
        }

    def from_dict(self, state: Dict[str, Any]) -> None:
        """Restore a pickled index."""
        fields = state["fields"].items()
        self.fields = {t: Field.from_dict(i) for t, i in fields}
        entities: List[str] = state.get("entities", [])
        self.entities = set((Identifier.get(e) for e in entities))

    def __len__(self) -> int:
        return len(self.entities)

    def __repr__(self) -> str:
        return "<Index(%r, %d, %d)>" % (
            self.view.scope.name,
            len(self.fields),
            len(self.entities),
        )
