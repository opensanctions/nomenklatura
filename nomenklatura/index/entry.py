import math
from typing import TYPE_CHECKING, Any, Dict, Generic, Optional

from nomenklatura.loader import DS, E

if TYPE_CHECKING:
    from nomenklatura.index.index import Index


class IndexEntry(Generic[DS, E]):
    """A set of entities and a weight associated with a given term in the index."""

    __slots__ = "index", "token", "idf", "entities", "frequencies"

    def __init__(self, index: "Index[DS, E]", token: str) -> None:
        self.index = index
        self.token = token
        self.idf: Optional[float] = None
        self.entities: Dict[str, float] = {}
        self.frequencies: Dict[str, float] = {}

    def add(self, entity_id: str, weight: float = 1.0) -> None:
        """Mark the given entity as relevant to the entry's token."""
        if entity_id not in self.entities:
            self.entities[entity_id] = 0
        self.entities[entity_id] += weight

    def remove(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)
        if not len(self):
            self.index.inverted.pop(self.token, None)

    def compute(self, min_terms: float) -> None:
        """Compute weighted term frequency for scoring."""
        self.idf = math.log(len(self.index) / len(self))
        self.frequencies = {}
        for entity_id, weight in self.entities.items():
            terms = self.index.terms.get(entity_id, 0)
            self.frequencies[entity_id] = weight / max(terms, min_terms)

    def __repr__(self) -> str:
        return "<IndexEntry(%r, %r)>" % (self.token, len(self))

    def __len__(self) -> int:
        return len(self.entities)

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            token=self.token,
            entities=self.entities,
        )

    @classmethod
    def from_dict(
        cls, index: "Index[DS, E]", data: Dict[str, Any]
    ) -> "IndexEntry[DS, E]":
        obj = cls(index, data["token"])
        obj.entities = data["entities"]
        return obj
