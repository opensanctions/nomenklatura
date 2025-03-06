import json
from typing import Any, Dict, Optional, Union

from sqlalchemy.engine import RowMapping

from nomenklatura.judgement import Judgement
from nomenklatura.resolver.identifier import Identifier, StrIdent


class Edge(object):
    __slots__ = (
        "key",
        "source",
        "target",
        "judgement",
        "score",
        "user",
        "created_at",
        "deleted_at",
    )

    def __init__(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        judgement: Judgement = Judgement.NO_JUDGEMENT,
        score: Optional[float] = None,
        user: Optional[str] = None,
        created_at: Optional[str] = None,
        deleted_at: Optional[str] = None,
    ):
        self.key = Identifier.pair(left_id, right_id)
        self.target, self.source = self.key
        self.judgement = judgement
        self.score = score
        self.user = user
        self.created_at = created_at
        self.deleted_at = deleted_at

    def other(self, cur: Identifier) -> Identifier:
        if cur == self.target:
            return self.source
        return self.target

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target": self.target.id,
            "source": self.source.id,
            "judgement": self.judgement.value,
            "score": self.score,
            "user": self.user,
            "created_at": self.created_at,
            "deleted_at": self.deleted_at,
        }

    def to_line(self) -> str:
        row = [
            self.target.id,
            self.source.id,
            self.judgement.value,
            self.score,
            self.user,
            self.created_at,
        ]
        return json.dumps(row) + "\n"

    def __str__(self) -> str:
        return self.to_line()

    def __hash__(self) -> int:
        return hash(self.key)

    def __eq__(self, other: Any) -> bool:
        return hash(self) == hash(other)

    def __lt__(self, other: Any) -> bool:
        return bool(self.key < other.key)

    def __repr__(self) -> str:
        return f"<E({self.target.id}, {self.source.id}, {self.judgement.value})>"

    @classmethod
    def from_line(cls, line: str) -> "Edge":
        data = json.loads(line)
        edge = cls(
            data[0],
            data[1],
            judgement=Judgement(data[2]),
            score=data[3],
            user=data[4],
            created_at=data[5],
        )
        if len(data) > 6:
            edge.deleted_at = data[6]
        return edge

    @classmethod
    def from_dict(cls, data: Union[RowMapping, Dict[str, Any]]) -> "Edge":
        return cls(
            left_id=data["target"],
            right_id=data["source"],
            judgement=Judgement(data["judgement"]),
            score=data["score"],
            user=data["user"],
            created_at=data.get("created_at"),
            deleted_at=data.get("deleted_at"),
        )
