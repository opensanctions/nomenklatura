from pydantic import BaseModel
from typing import List, Dict, Optional, Callable
from followthemoney.proxy import E, EntityProxy

Encoded = List[float]
CompareFunction = Callable[[EntityProxy, EntityProxy], float]


class FeatureDoc(BaseModel):
    """Documentation for a particular feature in the matching API model."""

    description: Optional[str]
    coefficient: float
    url: str


FeatureDocs = Dict[str, FeatureDoc]


class MatchingResult(BaseModel):
    """Score and feature comparison results for matching comparison."""

    score: float
    features: Dict[str, float]

    @classmethod
    def make(cls, score: float, features: Dict[str, float]) -> "MatchingResult":
        """Create a new matching result."""
        results = {k: v for k, v in features.items() if v is not None and v != 0.0}
        return cls(score=score, features=results)


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
