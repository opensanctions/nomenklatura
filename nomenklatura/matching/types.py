from typing import List, Dict, Optional, Callable
from typing_extensions import TypedDict
from followthemoney.proxy import E, EntityProxy

Encoded = List[float]
FeatureItem = Callable[[EntityProxy, EntityProxy], float]


class FeatureDoc(TypedDict):
    """Documentation for a particular feature in the matching API model."""

    description: Optional[str]
    coefficient: float
    url: str


FeatureDocs = Dict[str, FeatureDoc]


class MatchingResult(TypedDict):
    """Score and feature comparison results for matching comparison."""

    score: float
    features: Dict[str, float]


class ScoringAlgorithm(object):
    """An implementation of a scoring system that compares two entities."""

    NAME = "algorithm_name"

    @classmethod
    def compare(cls, query: E, match: E) -> MatchingResult:
        """Compare the two entities and return a score and feature comparison."""
        raise NotImplementedError

    @classmethod
    def explain(cls) -> FeatureDocs:
        """Return an explanation of the features and their coefficients."""
        raise NotImplementedError
