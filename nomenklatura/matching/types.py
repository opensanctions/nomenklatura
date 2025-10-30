from enum import Enum
from pydantic import BaseModel
from typing import List, Dict, Optional, Callable, Union, cast
from followthemoney.proxy import E, EntityProxy

from nomenklatura.matching.util import make_github_url, FNUL

Encoded = List[float]
CompareFunction = Callable[[EntityProxy, EntityProxy], float]
FeatureCompareFunction = Callable[[EntityProxy, EntityProxy], "FtResult"]
FeatureCompareConfigured = Callable[
    [EntityProxy, EntityProxy, "ScoringConfig"], "FtResult"
]


class FeatureDoc(BaseModel):
    """Documentation for a particular feature in the matching API model."""

    description: Optional[str]
    coefficient: float
    url: str


FeatureDocs = Dict[str, FeatureDoc]


class ConfigVarType(str, Enum):
    """The type of a configuration variable."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


class ConfigVar(BaseModel):
    """A configuration variable for a scoring algorithm."""

    type: ConfigVarType = ConfigVarType.FLOAT
    description: Optional[str] = None
    default: Union[str, int, float, bool, None] = 0


class AlgorithmDocs(BaseModel):
    """Documentation for a scoring algorithm."""

    name: str
    description: Optional[str] = None
    config: Dict[str, ConfigVar]
    features: FeatureDocs


class FtResult(BaseModel):
    """A explained score for a particular feature result."""

    detail: Optional[str]
    score: float

    def empty(self) -> bool:
        """Check if the result is empty."""
        return self.detail is None and self.score == FNUL

    @classmethod
    def wrap(cls, func: CompareFunction) -> FeatureCompareFunction:
        """Wrap a score and detail into a feature result."""

        def wrapper(query: E, result: E) -> "FtResult":
            return cls(score=func(query, result), detail=None)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    @classmethod
    def unwrap(cls, func: FeatureCompareConfigured) -> CompareFunction:
        """Unwrap a feature result returned by a comparator into a score."""
        config = ScoringConfig.defaults()

        def wrapper(query: E, result: E) -> float:
            return func(query, result, config).score

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    def __repr__(self) -> str:
        """Return a string representation of the feature result."""
        return f"<FtR({self.score}, {self.detail!r})>"


class MatchingResult(BaseModel):
    """Score and feature comparison results for matching comparison."""

    score: float
    features: Dict[str, float]
    explanations: Dict[str, FtResult]

    @classmethod
    def make(cls, score: float, explanations: Dict[str, FtResult]) -> "MatchingResult":
        """Create a new matching result."""
        explanations = {k: v for k, v in explanations.items() if not v.empty()}
        features = {k: v.score for k, v in explanations.items() if v.score != FNUL}
        return cls(score=score, features=features, explanations=explanations)

    def __repr__(self) -> str:
        """Return a string representation of the matching result."""
        return f"<MR({self.score}, expl={self.explanations})>"


class ScoringConfig(BaseModel):
    """Configuration for a scoring algorithm."""

    weights: Dict[str, float]
    config: Dict[str, Union[str, int, float, bool, None]]

    @classmethod
    def defaults(cls) -> "ScoringConfig":
        """Return the default configuration."""
        return cls(weights={}, config={})

    def get_float(self, key: str) -> float:
        """Get a float value from the configuration."""
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"{key} cannot be None")
        return float(value)

    def get_optional_string(self, key: str) -> Optional[str]:
        """Get a string value from the configuration."""
        value = self.config.get(key)
        if value is None:
            return value
        return str(value)

    def __hash__(self) -> int:
        return hash(self.model_dump_json())


class ScoringAlgorithm(object):
    """An implementation of a scoring system that compares two entities."""

    NAME = "algorithm_name"
    CONFIG: Dict[str, ConfigVar] = {}

    @classmethod
    def compare(cls, query: E, result: E, config: ScoringConfig) -> MatchingResult:
        """Compare the two entities and return a score and feature comparison."""
        raise NotImplementedError

    @classmethod
    def get_feature_docs(cls) -> FeatureDocs:
        """Return an explanation of the features and their coefficients."""
        raise NotImplementedError

    @classmethod
    def get_docs(cls) -> AlgorithmDocs:
        """Return an explanation of the algorithm and its features."""
        return AlgorithmDocs(
            name=cls.NAME,
            description=cls.__doc__,
            config=cls.CONFIG,
            features=cls.get_feature_docs(),
        )

    @classmethod
    def default_config(cls) -> ScoringConfig:
        """Return the default configuration for the algorithm."""
        return ScoringConfig.defaults()


class Feature(BaseModel):
    func: Union[FeatureCompareFunction, FeatureCompareConfigured]
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

    def invoke(self, query: E, result: E, config: ScoringConfig) -> FtResult:
        """Invoke the feature function and return the result."""
        if self.func.__code__.co_argcount == 3:
            func = cast(FeatureCompareConfigured, self.func)
            return func(query, result, config)
        else:
            func = cast(FeatureCompareFunction, self.func)  # type: ignore
            return func(query, result)  # type: ignore


class HeuristicAlgorithm(ScoringAlgorithm):
    features: List[Feature]

    @classmethod
    def compute_score(
        cls, scores: Dict[str, float], weights: Dict[str, float]
    ) -> float:
        raise NotImplementedError

    @classmethod
    def get_feature_docs(cls) -> FeatureDocs:
        return {f.name: f.doc for f in cls.features}

    @classmethod
    def default_config(cls) -> ScoringConfig:
        """Return the default configuration for the algorithm."""
        config = ScoringConfig.defaults()
        for name, var in cls.CONFIG.items():
            config.config[name] = var.default
        return config

    @classmethod
    def compare(cls, query: E, result: E, config: ScoringConfig) -> MatchingResult:
        if not query.schema.can_match(result.schema):
            if not query.schema.name == result.schema.name:
                return MatchingResult.make(FNUL, {})

        for name, var in cls.CONFIG.items():
            if config.config.get(name) is None:
                config.config[name] = var.default

        explanations: Dict[str, FtResult] = {}
        scores: Dict[str, float] = {}
        weights: Dict[str, float] = {}
        for feature in cls.features:
            weights[feature.name] = config.weights.get(feature.name, feature.weight)
            if weights[feature.name] != FNUL:
                explanations[feature.name] = feature.invoke(query, result, config)
                scores[feature.name] = explanations[feature.name].score
        score = cls.compute_score(scores, weights)
        score = min(1.0, max(FNUL, score))
        return MatchingResult.make(score=score, explanations=explanations)
