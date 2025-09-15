import re

from typing import Optional, Any, Sequence
from rigour.names import NamePart, Symbol, NamePartTag


class Match:
    """A Match combines query and result name parts, along with a score and weight. It is one
    part of the matching result, which is eventually aggregated into a final score."""

    __slots__ = ["qps", "rps", "symbol", "score", "weight"]

    def __init__(
        self,
        qps: Sequence[NamePart] = [],
        rps: Sequence[NamePart] = [],
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

    @property
    def qstr(self) -> str:
        """Get the query string representation."""
        return " ".join([part.comparable for part in self.qps])

    @property
    def rstr(self) -> str:
        """Get the result string representation."""
        return " ".join([part.comparable for part in self.rps])

    def is_family_name(self) -> bool:
        """Check if the match represents a family name."""
        for np in self.qps:
            if np.tag == NamePartTag.FAMILY:
                return True
        for np in self.rps:
            if np.tag == NamePartTag.FAMILY:
                return True
        return False

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
        qps_str = self.qstr
        rps_str = self.rstr
        if self.symbol is not None:
            explanation = f"{qps_str!r}≈{rps_str!r} symbolMatch {self.symbol}"
        elif not len(qps_str):
            explanation = f"{rps_str!r} extraResultPart"
        elif not len(rps_str):
            explanation = f"{qps_str!r} extraQueryPart"
        elif qps_str == rps_str:
            explanation = f"{rps_str!r} literalMatch"
        else:
            explanation = f"{qps_str!r}≈{rps_str!r} fuzzyMatch"
        return f"[{explanation}: {self.score:.2f}, weight {self.weight:.2f}]"


NUMERIC = re.compile(r"\d{1,}")


def numbers_mismatch(query: str, result: str) -> bool:
    """Check if the number of numerals in two names is different."""
    query_nums = set(NUMERIC.findall(query))
    result_nums = set(NUMERIC.findall(result))
    return len(query_nums.difference(result_nums)) > 0
