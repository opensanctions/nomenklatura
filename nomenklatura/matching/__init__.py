from typing import List, Type, Optional
from nomenklatura.matching.v1.model import MatcherV1
from nomenklatura.matching.v1.train import train_matcher as train_v1_matcher
from nomenklatura.matching.v2.model import MatcherV2
from nomenklatura.matching.v2.train import train_matcher as train_v2_matcher
from nomenklatura.matching.heuristic import NameMatcher, NameQualifiedMatcher
from nomenklatura.matching.types import ScoringAlgorithm

ALGORITHMS: List[Type[ScoringAlgorithm]] = [
    MatcherV1,
    MatcherV2,
    NameMatcher,
    NameQualifiedMatcher,
]

DefaultAlgorithm = MatcherV2


def get_algorithm(name: str) -> Optional[Type[ScoringAlgorithm]]:
    """Return the scoring algorithm class with the given name."""
    for algorithm in ALGORITHMS:
        if algorithm.NAME == name:
            return algorithm
    return None


__all__ = [
    "MatcherV1",
    "train_v1_matcher",
    "MatcherV2",
    "train_v2_matcher",
    "DefaultAlgorithm",
    "ScoringAlgorithm",
    "OFAC249Matcher",
    "OFAC249QualifiedMatcher",
]
