from collections.abc import Callable
from enum import Enum
from typing import ClassVar, cast

from followthemoney import E, EntityProxy
from pydantic import BaseModel

from nomenklatura.matching.util import FNUL, make_github_url

Encoded = list[float]
CompareFunction = Callable[[EntityProxy, EntityProxy], float]
FeatureCompareFunction = Callable[[EntityProxy, EntityProxy], "FtResult"]
FeatureCompareConfigured = Callable[
    [EntityProxy, EntityProxy, "ScoringConfig"], "FtResult"
]


class FeatureDoc(BaseModel):
    """Documentation for a particular feature in the matching API model."""

    description: str | None
    coefficient: float
    url: str


FeatureDocs = dict[str, FeatureDoc]


class ConfigVarType(str, Enum):
    """The type of a configuration variable."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


class ConfigVar(BaseModel):
    """A configuration variable for a scoring algorithm."""

    type: ConfigVarType = ConfigVarType.FLOAT
    description: str | None = None
    default: str | int | float | bool | None = 0


class AlgorithmDocs(BaseModel):
    """Documentation for a scoring algorithm."""

    name: str
    description: str | None = None
    config: dict[str, ConfigVar]
    features: FeatureDocs


class FtResult:
    """Match feature result type."""

    __slots__ = ["candidate", "detail", "query", "score"]

    def __init__(
        self,
        score: float,
        detail: str | None = None,
        query: str | None = None,
        candidate: str | None = None,
    ) -> None:
        self.score = score
        self.detail = detail

        # Used e.g. for names and identifiers to explain which value from
        # the query and result entities was actually used to make the match.
        self.query = query
        self.candidate = candidate

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


class FeatureResult(BaseModel):
    """A explained score for a particular feature result."""

    # This is the API version of the explanation. it's a pydantic model that can
    # be easily serialized to JSON and returned in the API response. The FtResult
    # is the internal version that is quicker to generate in the millions during
    # matching operations.

    detail: str | None
    score: float

    # Used e.g. for names and identifiers to explain which value from
    # the query and result entities was actually used to make the match.
    query: str | None = None
    candidate: str | None = None


class MatchingResult:
    """Score and feature comparison results for matching comparison. This is instantiated
    for each candidate returned by the search, and the score is used to rank the results.
    Explanations are lazy-generated for performance."""

    __slots__ = ["_explanations", "score"]

    def __init__(self, score: float, explanations: dict[str, FtResult]) -> None:
        self.score = score
        self._explanations = explanations

    @property
    def explanations(self) -> dict[str, FeatureResult]:
        """Return the explanations for the feature results as pydantic models."""
        _explanations: dict[str, FeatureResult] = {}
        for name, res in self._explanations.items():
            if res.detail is not None or res.score > FNUL:
                _explanations[name] = FeatureResult(
                    score=res.score,
                    detail=res.detail,
                    query=res.query,
                    candidate=res.candidate,
                )
        return _explanations

    def __repr__(self) -> str:
        """Return a string representation of the matching result."""
        return f"<MR({self.score}, expl={self._explanations})>"


class ScoringConfig(BaseModel):
    """Configuration for a scoring algorithm."""

    weights: dict[str, float]
    config: dict[str, str | int | float | bool | None]

    @classmethod
    def defaults(cls) -> "ScoringConfig":
        """Return the default configuration."""
        return cls.model_construct(weights={}, config={})

    def get_float(self, key: str) -> float:
        """Get a float value from the configuration."""
        value = self.config.get(key)
        if value is None:
            raise ValueError(f"{key} cannot be None")
        return float(value)

    def get_optional_string(self, key: str) -> str | None:
        """Get a string value from the configuration."""
        value = self.config.get(key)
        if value is None:
            return value
        return str(value)

    def __hash__(self) -> int:
        return hash(self.model_dump_json())


class ScoringAlgorithm:
    """An implementation of a scoring system that compares two entities."""

    NAME = "algorithm_name"
    CONFIG: ClassVar[dict[str, ConfigVar]] = {}

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


class Feature:
    __slots__ = ["func", "name", "qualifier", "weight"]

    def __init__(
        self,
        func: FeatureCompareFunction | FeatureCompareConfigured,
        weight: float,
        qualifier: bool = False,
    ) -> None:
        self.func = func
        self.name = func.__name__
        self.weight = weight
        self.qualifier = qualifier

    def get_doc(self) -> FeatureDoc:
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
            func = cast("FeatureCompareConfigured", self.func)
            return func(query, result, config)
        func = cast("FeatureCompareFunction", self.func)  # type: ignore[assignment]
        return func(query, result)  # type: ignore[call-arg]


class HeuristicAlgorithm(ScoringAlgorithm):
    features: ClassVar[list[Feature]]

    @classmethod
    def compute_score(
        cls, scores: dict[str, float], weights: dict[str, float]
    ) -> float:
        raise NotImplementedError

    @classmethod
    def get_feature_docs(cls) -> FeatureDocs:
        return {f.name: f.get_doc() for f in cls.features}

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
                return MatchingResult(FNUL, {})

        for name, var in cls.CONFIG.items():
            if config.config.get(name) is None:
                config.config[name] = var.default

        explanations: dict[str, FtResult] = {}
        scores: dict[str, float] = {}
        weights: dict[str, float] = {}

        for feature in cls.features:
            if feature.qualifier:
                continue
            weights[feature.name] = config.weights.get(feature.name, feature.weight)
            if weights[feature.name] != FNUL:
                func = cast("FeatureCompareConfigured", feature.func)
                res = func(query, result, config)
                if res is not None:
                    explanations[feature.name] = res
                    scores[feature.name] = res.score

        # Qualifier features have only negative weights (except a small address
        # bonus). Skip them when no main feature scored above zero, since they
        # cannot improve the result. When scores is empty (all main weights
        # overridden to zero), qualifiers are still evaluated.
        if max(scores.values(), default=FNUL) <= FNUL:
            return MatchingResult(score=FNUL, explanations=explanations)

        for feature in cls.features:
            if not feature.qualifier:
                continue
            weights[feature.name] = config.weights.get(feature.name, feature.weight)
            if weights[feature.name] != FNUL:
                func = cast("FeatureCompareConfigured", feature.func)
                res = func(query, result, config)
                if res is not None:
                    explanations[feature.name] = res
                    scores[feature.name] = res.score

        score = cls.compute_score(scores, weights)
        score = min(1.0, max(FNUL, score))
        return MatchingResult(score=score, explanations=explanations)
