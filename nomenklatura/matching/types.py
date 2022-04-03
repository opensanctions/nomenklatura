from typing import Dict, Optional, Tuple, TypedDict, cast


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
