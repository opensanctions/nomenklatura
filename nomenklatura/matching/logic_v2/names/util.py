import re

from typing import List, Optional, Any
from rigour.names import NamePart, Symbol


class Match:
    """A Match combines query and result name parts, along with a score and weight. It is one
    part of the matching result, which is eventually aggregated into a final score."""

    __slots__ = ["qps", "rps", "symbol", "score", "weight"]

    def __init__(
        self,
        qps: List[NamePart] = [],
        rps: List[NamePart] = [],
        symbol: Optional[Symbol] = None,
        score: float = 0.0,
        weight: float = 1.0,
    ) -> None:
        """Initialize the Match object with query and result parts."""
        self.qps = list(qps)
        self.rps = list(rps)
        self.symbol: Optional[Symbol] = symbol
        self.score = score
        self.weight = weight

    @property
    def weighted_score(self) -> float:
        """Calculate the weighted score."""
        return self.score * self.weight

    def __hash__(self) -> int:
        """Hash the Match object based on query and result parts."""
        return hash((self.symbol, tuple(self.qps), tuple(self.rps)))

    def __eq__(self, other: Any) -> bool:
        """Check equality of two Match objects based on query and result parts."""
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        """String representation of the Match object."""
        return f"<Match({str(self)})>"

    def __str__(self) -> str:
        """String representation of the Match object for debugging."""
        if self.symbol is not None:
            return str(self.symbol)
        qps_str = " ".join([part.comparable for part in self.qps])
        rps_str = " ".join([part.comparable for part in self.rps])
        if not len(qps_str):
            return f"[+{rps_str}]"
        if not len(rps_str):
            return f"[-{qps_str}]"
        if qps_str == rps_str:
            return f"[={rps_str}]"
        score_str = f"{self.score:.2f}".lstrip("0")
        return f"[{qps_str}<{score_str}>{rps_str}]"


NUMERIC = re.compile(r"\d{1,}")


def numbers_mismatch(query: str, result: str) -> bool:
    """Check if the number of numerals in two names is different."""
    query_nums = set(NUMERIC.findall(query))
    result_nums = set(NUMERIC.findall(result))
    return len(query_nums.difference(result_nums)) > 0
