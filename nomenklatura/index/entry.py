from typing import TYPE_CHECKING, Any, Dict, Generic, Iterable, Tuple
from nomenklatura.loader import DS, E

if TYPE_CHECKING:
    from nomenklatura.index.index import Index


class IndexEntry(Generic[DS, E]):
    """A set of entities and a weight associated with a given term in the index."""

    __slots__ = "index", "token", "weight", "entities", "frequencies"

    def __init__(self, index: "Index[DS, E]", token: str, weight: float = 1.0) -> None:
        self.index = index
        self.token = token
        self.weight: float = weight
        self.entities: Dict[str, int] = {}
        self.frequencies: Dict[str, float] = {}

    def add(self, entity_id: str) -> None:
        """Mark the given entity as relevant to the entry's token."""
        if entity_id not in self.entities:
            self.entities[entity_id] = 0
        self.entities[entity_id] += 1

    def remove(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)
        if not len(self):
            self.index.inverted.pop(self.token, None)

    def compute(self) -> None:
        """Compute weighted term frequency for scoring."""
        self.frequencies = {}
        for entity_id, count in self.entities.items():
            terms = self.index.terms.get(entity_id, 0)
            tf = self.weight * count
            self.frequencies[entity_id] = tf / max(terms, 1)

    def all_tf(self) -> Iterable[Tuple[str, float]]:
        return self.frequencies.items()

    def __repr__(self) -> str:
        return "<IndexEntry(%r, %r)>" % (self.token, self.weight)

    def __len__(self) -> int:
        return len(self.entities)

    def to_dict(self) -> Dict[str, Any]:
        return dict(
            token=self.token,
            weight=self.weight,
            entities=self.entities,
        )

    @classmethod
    def from_dict(
        cls, index: "Index[DS, E]", data: Dict[str, Any]
    ) -> "IndexEntry[DS, E]":
        obj = cls(index, data["token"], weight=data["weight"])
        obj.entities = data["entities"]
        return obj
