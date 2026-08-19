from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.erun.train import train_matcher as train_erun_matcher
from nomenklatura.matching.logic_v1.model import LogicV1
from nomenklatura.matching.logic_v2.model import LogicV2
from nomenklatura.matching.name_based import (
    NameMatcher,
    NameQualifiedMatcher,
    OFACMatcher,
)
from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.matching.regression_v1.train import train_matcher as train_v1_matcher
from nomenklatura.matching.types import ScoringAlgorithm, ScoringConfig

ALGORITHMS: list[type[ScoringAlgorithm]] = [
    LogicV1,
    LogicV2,
    NameMatcher,
    NameQualifiedMatcher,
    OFACMatcher,
    RegressionV1,
    EntityResolveRegression,
]

DefaultAlgorithm = RegressionV1
DedupeAlgorithm = EntityResolveRegression


def get_algorithm(name: str) -> type[ScoringAlgorithm] | None:
    """Return the scoring algorithm class with the given name."""
    for algorithm in ALGORITHMS:
        if name == algorithm.NAME:
            return algorithm
    return None


__all__ = [
    "DedupeAlgorithm",
    "DefaultAlgorithm",
    "EntityResolveRegression",
    "LogicV1",
    "LogicV2",
    "NameMatcher",
    "NameQualifiedMatcher",
    "OFACMatcher",
    "RegressionV1",
    "ScoringAlgorithm",
    "ScoringConfig",
    "train_erun_matcher",
    "train_v1_matcher",
]
