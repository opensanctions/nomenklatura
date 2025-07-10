from typing import List, Optional, Any
from rigour.names import NamePart
from rigour.names import tokenize_name, prenormalize_name


class Match:
    __slots__ = ["qps", "rps", "text", "score", "weight"]

    def __init__(self, qps: List[NamePart] = [], rps: List[NamePart] = []) -> None:
        """Initialize the Match object with query and result parts."""
        self.qps = list(qps)
        self.rps = list(rps)
        self.text: Optional[str] = None
        self.score = 0.0
        self.weight = 1.0

    @property
    def weighted_score(self) -> float:
        """Calculate the weighted score."""
        return self.score * self.weight

    def __hash__(self) -> int:
        """Hash the Match object based on query and result parts."""
        return hash((tuple(self.qps), tuple(self.rps)))

    def __eq__(self, other: Any) -> bool:
        """Check equality of two Match objects based on query and result parts."""
        return hash(self) == hash(other)

    def __repr__(self) -> str:
        """String representation of the Match object."""
        return f"<Match({str(self)})>"

    def __str__(self) -> str:
        """String representation of the Match object for debugging."""
        if self.text is not None:
            return self.text
        qps_str = " ".join(part.comparable for part in self.qps)
        rps_str = " ".join(part.comparable for part in self.rps)
        if not len(qps_str):
            return f"r:{rps_str}"
        if not len(rps_str):
            return f"q:{qps_str}"
        if self.score == 1.0:
            return f"={rps_str}"
        return f"{qps_str}~{self.score:.2f}~{rps_str}"


def normalize_name(name: Optional[str]) -> str:
    """Normalize a name for tokenization and matching."""
    norm = prenormalize_name(name)
    return " ".join(tokenize_name(norm))


def name_normalizer(name: Optional[str]) -> Optional[str]:
    """Same as before, but meeting the definition of a rigour Normalizer."""
    if name is None:
        return None
    name = normalize_name(name)
    if len(name) == 0:
        return None
    return name
