import math
from typing import Any, Dict, Generator, Tuple, cast


class Entry(object):
    """A set of entities and a weight associated with a given term in the index."""

    __slots__ = "idf", "entities"

    def __init__(self) -> None:
        self.idf: float = 0.0
        self.entities: Dict[str, int] = dict()

    def add(self, entity_id: str) -> None:
        """Mark the given entity as relevant to the entry's token."""
        # This is insane and meant to trade perf for memory:
        try:
            self.entities[entity_id] += 1
        except KeyError:
            self.entities[entity_id] = 1

    def compute(self, field: "Field") -> None:
        """Compute weighted term frequency for scoring."""
        # lene = len(self.entities)
        # idf = 1 + ((field.len - lene + 0.5) / (lene + 0.5))
        # self.idf = math.log(idf)
        self.idf = math.log(field.len / len(self.entities))

    def frequencies(self, field: "Field") -> Generator[Tuple[str, float], None, None]:
        # https://www.elastic.co/blog/practical-bm25-part-2-the-bm25-algorithm-and-its-variables
        # k1 = 1.2
        # b = 0.75
        for entity_id, mentions in self.entities.items():
            field_len = max(1, field.entities[entity_id])
            yield entity_id, (mentions / field_len)
            # try:
            #     field_len = max(1, field.entities[entity_id])
            #     # tf = weight / max(1, terms)
            #     len_coeff = 1 - b + b * (field_len / field.avg_len)
            #     tf = (mentions * (k1 + 1)) / (mentions + k1 * len_coeff)
            #     yield entity_id, tf
            # except KeyError:
            #     continue

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
        self.entities: Dict[str, int] = {}

    def add(self, entity_id: str, token: str) -> None:
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

        for entry in self.tokens.values():
            entry.compute(self)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tokens": {t: e.to_dict() for t, e in self.tokens.items()},
            "entities": self.entities,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Field":
        obj = cls()
        inverted = data["tokens"].items()
        obj.tokens = {t: Entry.from_dict(i) for t, i in inverted}
        obj.entities = cast(Dict[str, int], data.get("entities"))
        return obj

    def __repr__(self) -> str:
        return "<Field(%d, %.3f)>" % (self.len, self.avg_len)
