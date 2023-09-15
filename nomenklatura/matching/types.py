from pydantic import BaseModel
from typing import List, Dict, Optional, Callable
from followthemoney.proxy import E, EntityProxy

from nomenklatura.matching.util import make_github_url

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
    def compare(cls, query: E, result: E) -> MatchingResult:
        """Compare the two entities and return a score and feature comparison."""
        raise NotImplementedError

    @classmethod
    def explain(cls) -> FeatureDocs:
        """Return an explanation of the features and their coefficients."""
        raise NotImplementedError


class Feature(BaseModel):
    func: CompareFunction
    weight: float
    qualifier: bool = False

    @property
    def name(self) -> str:
        return self.func.__name__

    @property
    def doc(self) -> FeatureDoc:
        description = self.func.__doc__
        assert description is not None, self.func.__name__
        return FeatureDoc(
            description=description,
            coefficient=self.weight,
            url=make_github_url(self.func),
        )


class HeuristicAlgorithm(ScoringAlgorithm):
    features: List[Feature]

    @classmethod
    def compute_score(cls, weights: Dict[str, float]) -> float:
        raise NotImplementedError

    @classmethod
    def explain(cls) -> FeatureDocs:
        return {f.name: f.doc for f in cls.features}

    @classmethod
    def compare(cls, query: E, result: E) -> MatchingResult:
        if not query.schema.can_match(result.schema):
            if not query.schema.name == result.schema.name:
                return MatchingResult.make(0.0, {})
        feature_weights: Dict[str, float] = {}
        for feature in cls.features:
            feature_weights[feature.name] = feature.func(query, result)
        score = cls.compute_score(feature_weights)
        score = min(1.0, max(0.0, score))
        # print(feature_weights)
        return MatchingResult.make(score=score, features=feature_weights)
