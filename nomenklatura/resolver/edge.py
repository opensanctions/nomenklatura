import json
from typing import Any, Optional

from nomenklatura.judgement import Judgement
from nomenklatura.resolver.identifier import Identifier, StrIdent


class Edge(object):

    __slots__ = ("key", "source", "target", "judgement", "score", "user", "timestamp")

    def __init__(
        self,
        left_id: StrIdent,
        right_id: StrIdent,
        judgement: Judgement = Judgement.NO_JUDGEMENT,
        score: Optional[float] = None,
        user: Optional[str] = None,
        timestamp: Optional[str] = None,
    ):
        self.key = Identifier.pair(left_id, right_id)
        self.target, self.source = self.key
        self.judgement = judgement
        self.score = score
        self.user = user
        self.timestamp = timestamp

    def other(self, cur: Identifier) -> Identifier:
        if cur == self.target:
            return self.source
        return self.target

    def to_line(self) -> str:
        row = [
            self.target.id,
            self.source.id,
            self.judgement.value,
            self.score,
            self.user,
            self.timestamp,
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
        return cls(
            data[0],
            data[1],
            judgement=Judgement(data[2]),
            score=data[3],
            user=data[4],
            timestamp=data[5],
        )
