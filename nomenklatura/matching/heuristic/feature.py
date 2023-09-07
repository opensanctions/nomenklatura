from typing import List, Dict
from pydantic import BaseModel
from followthemoney.proxy import E

from nomenklatura.matching.types import CompareFunction, FeatureDoc, FeatureDocs
from nomenklatura.matching.types import ScoringAlgorithm, MatchingResult
from nomenklatura.matching.util import make_github_url


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
    def compare(cls, query: E, match: E) -> MatchingResult:
        if not query.schema.can_match(match.schema):
            if not query.schema.name == match.schema.name:
                return MatchingResult.make(0.0, {})
        feature_weights: Dict[str, float] = {}
        for feature in cls.features:
            feature_weights[feature.name] = feature.func(query, match)
        score = cls.compute_score(feature_weights)
        score = min(1.0, max(0.0, score))
        return MatchingResult.make(score, feature_weights)
