from typing import List, Type, Optional
from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.matching.regression_v1.train import train_matcher as train_v1_matcher
from nomenklatura.matching.regression_v2.model import RegressionV2
from nomenklatura.matching.regression_v2.train import train_matcher as train_v2_matcher
from nomenklatura.matching.name_based import NameMatcher, NameQualifiedMatcher
from nomenklatura.matching.logic import LogicV1
from nomenklatura.matching.types import ScoringAlgorithm

ALGORITHMS: List[Type[ScoringAlgorithm]] = [
    LogicV1,
    NameMatcher,
    NameQualifiedMatcher,
    RegressionV1,
    RegressionV2,
]

DefaultAlgorithm = RegressionV2


def get_algorithm(name: str) -> Optional[Type[ScoringAlgorithm]]:
    """Return the scoring algorithm class with the given name."""
    for algorithm in ALGORITHMS:
        if algorithm.NAME == name:
            return algorithm
    return None


__all__ = [
    "RegressionV1",
    "train_v1_matcher",
    "RegressionV2",
    "train_v2_matcher",
    "DefaultAlgorithm",
    "ScoringAlgorithm",
    "NameMatcher",
    "NameQualifiedMatcher",
    "LogicV1",
]
