from typing import Any, Union

import shortuuid
from rigour.ids.wikidata import is_qid

from nomenklatura.resolver.common import ResolverLogicError

StrIdent = Union[str, "Identifier"]
Pair = tuple["Identifier", "Identifier"]


class Identifier:
    PREFIX = "NK-"

    __slots__ = ("canonical", "id", "weight")

    def __init__(self, id: str):
        self.id = id
        self.weight: int = 1
        if self.id.startswith(self.PREFIX):
            self.weight = 2
        elif is_qid(id):
            self.weight = 3
        self.canonical = self.weight > 1

    def __eq__(self, other: object) -> bool:
        return self.id == str(other)

    def __lt__(self, other: Any) -> bool:
        return (self.weight, self.id) < (other.weight, other.id)

    def __str__(self) -> str:
        return self.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __len__(self) -> int:
        return len(self.id)

    def __repr__(self) -> str:
        return f"<I({self.id})>"

    @classmethod
    def get(cls, id: StrIdent) -> "Identifier":
        if isinstance(id, str):
            return cls(id)
        return id

    @classmethod
    def pair(cls, left_id: StrIdent, right_id: StrIdent) -> Pair:
        left = cls.get(left_id)
        right = cls.get(right_id)
        if left == right:
            raise ResolverLogicError("%s/%s" % (left, right))
        return (max(left, right), min(left, right))

    @classmethod
    def make(cls, value: str | None = None) -> "Identifier":
        key = value or shortuuid.uuid()
        return cls.get(f"{cls.PREFIX}{key}")
