from typing import Dict, Optional, TypedDict, Callable
from nomenklatura.entity import CompositeEntity as Entity


FeatureItem = Callable[[Entity, Entity], float]


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
