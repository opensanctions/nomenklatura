from nomenklatura.matching.v1.model import MatcherV1
from nomenklatura.matching.v1.train import train_matcher as train_v1_matcher
from nomenklatura.matching.v2.model import MatcherV2
from nomenklatura.matching.v2.train import train_matcher as train_v2_matcher
from nomenklatura.matching.ofac import OFAC249Matcher, OFAC249QualifiedMatcher

ALGORITHMS = [
    "MatcherV1",
    "MatcherV2",
    "OFAC249Matcher",
    "OFAC249QualifiedMatcher",
]

__all__ = [
    "MatcherV1",
    "train_v1_matcher",
    "MatcherV2",
    "train_v2_matcher",
    "OFAC249Matcher",
    "OFAC249QualifiedMatcher",
]
