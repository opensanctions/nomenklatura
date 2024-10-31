import math
from typing import Any, Dict, Generator, Tuple

from nomenklatura.resolver import Identifier


class Entry(object):
    """A set of entities and a weight associated with a given term in the index."""

    __slots__ = "idf", "entities"

    def __init__(self) -> None:
        self.entities: Dict[Identifier, int] = dict()

    def add(self, entity_id: Identifier) -> None:
        """Mark the given entity as relevant to the entry's token."""
        # This is insane and meant to trade perf for memory:
        try:
            self.entities[entity_id] += 1
        except KeyError:
            self.entities[entity_id] = 1

    def frequencies(
        self, field: "Field"
    ) -> Generator[Tuple[Identifier, float], None, None]:
        """
        Term Frequency (TF) for each entity in this entry.

        TF being the number of occurrences of this token in the entity divided
        by the total number of tokens in the entity (scoped to this field).
        """
        for entity_id, mentions in self.entities.items():
            field_len = max(1, field.entities[entity_id])
            yield entity_id, (mentions / field_len)

    def __repr__(self) -> str:
        return "<Entry(%r)>" % len(self.entities)

    def to_dict(self) -> Dict[str, Any]:
        return {"entities": self.entities}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Entry":
        obj = cls()
        obj.entities = data["entities"]
        return obj


class Field(object):
    """Index of all tokens of the same type."""

    __slots__ = "len", "avg_len", "tokens", "entities"

    def __init__(self) -> None:
        self.len = 0
        self.avg_len = 0.0
        self.tokens: Dict[str, Entry] = {}
        self.entities: Dict[Identifier, int] = {}

    def add(self, entity_id: Identifier, token: str) -> None:
        if token not in self.tokens:
            self.tokens[token] = Entry()
        self.tokens[token].add(entity_id)
        try:
            self.entities[entity_id] += 1
        except KeyError:
            self.entities[entity_id] = 1

    def compute(self) -> None:
        self.len = max(1, len(self.entities))
        self.avg_len = sum(self.entities.values()) / self.len

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens": {t: e.to_dict() for t, e in self.tokens.items()},
            "entities": {i.id: c for i, c in self.entities.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Field":
        obj = cls()
        inverted = data["tokens"].items()
        obj.tokens = {t: Entry.from_dict(i) for t, i in inverted}
        # obj.entities = cast(Dict[str, int], data.get("entities"))
        entities: Dict[str, int] = data.get("entities", {})
        obj.entities = {Identifier.get(e): c for e, c in entities.items()}
        return obj

    def __repr__(self) -> str:
        return "<Field(%d, %.3f)>" % (self.len, self.avg_len)
