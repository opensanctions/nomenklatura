import pickle
from functools import cache
from typing import ClassVar, cast

import numpy as np
from followthemoney import E
from sklearn.pipeline import Pipeline  # type: ignore[import-untyped]

from nomenklatura.matching.erun.countries import (
    org_country_mismatch,
    per_country_mismatch,
    position_country_match,
)
from nomenklatura.matching.erun.dob import dob_match, dob_year_match
from nomenklatura.matching.erun.identifiers import (
    strong_identifier_match,
    weak_identifier_match,
)
from nomenklatura.matching.erun.misc import (
    address_match,
    address_number_disagreement,
    address_number_overlap,
    birth_place,
    contact_match,
    gender_mismatch,
    security_isin_mismatch,
)
from nomenklatura.matching.erun.names import (
    family_name_match,
    legal_name_levenshtein,
    name_numbers,
    name_token_overlap,
    obj_name_levenshtein,
    org_name_levenshtein,
    person_name_levenshtein,
)
from nomenklatura.matching.types import (
    CompareFunction,
    Encoded,
    FeatureDoc,
    FeatureDocs,
    FtResult,
    MatchingResult,
    ScoringAlgorithm,
    ScoringConfig,
)
from nomenklatura.matching.util import make_github_url
from nomenklatura.util import DATA_PATH


class EntityResolveRegression(ScoringAlgorithm):
    """Entity resolution matcher. Do not use this in (regulated) screening scenarios."""

    NAME = "er-unstable"
    MODEL_PATH = DATA_PATH.joinpath(f"{NAME}.pkl")
    FEATURES: ClassVar[list[CompareFunction]] = [
        name_token_overlap,
        name_numbers,
        legal_name_levenshtein,
        person_name_levenshtein,
        org_name_levenshtein,
        strong_identifier_match,
        weak_identifier_match,
        dob_match,
        dob_year_match,
        contact_match,
        family_name_match,
        birth_place,
        gender_mismatch,
        per_country_mismatch,
        position_country_match,
        org_country_mismatch,
        security_isin_mismatch,
        obj_name_levenshtein,
        address_match,
        address_number_overlap,
        address_number_disagreement,
    ]

    @classmethod
    def save(cls, pipe: Pipeline, coefficients: dict[str, float]) -> None:
        """Store a classification pipeline after training."""
        mdl = pickle.dumps({"pipe": pipe, "coefficients": coefficients})
        with open(cls.MODEL_PATH, "wb") as fh:
            fh.write(mdl)
        cls.load.cache_clear()

    @classmethod
    @cache
    def load(cls) -> tuple[Pipeline, dict[str, float]]:
        """Load a pre-trained classification pipeline for ad-hoc use."""
        with open(cls.MODEL_PATH, "rb") as fh:
            matcher = pickle.loads(fh.read())
        pipe = cast("Pipeline", matcher["pipe"])
        coefficients = cast("dict[str, float]", matcher["coefficients"])
        current = [f.__name__ for f in cls.FEATURES]
        if list(coefficients.keys()) != current:
            raise RuntimeError("Model was not trained on identical features!")
        return pipe, coefficients

    @classmethod
    def get_feature_docs(cls) -> FeatureDocs:
        """Return an explanation of the features and their coefficients."""
        features: FeatureDocs = {}
        _, coefficients = cls.load()
        for func in cls.FEATURES:
            name = func.__name__
            features[name] = FeatureDoc(
                description=func.__doc__,
                coefficient=float(coefficients[name]),
                url=make_github_url(func),
            )
        return features

    @classmethod
    def compare(cls, query: E, result: E, config: ScoringConfig) -> MatchingResult:
        """Use a regression model to compare two entities."""
        pipe, _ = cls.load()
        encoded = cls.encode_pair(query, result)
        npfeat = np.array([encoded])
        pred = pipe.predict_proba(npfeat)
        score = float(pred[0][1])
        explanations: dict[str, FtResult] = {}
        for feature, coeff in zip(cls.FEATURES, encoded, strict=True):
            name = feature.__name__
            explanations[name] = FtResult(score=float(coeff), detail=None)
        return MatchingResult(score=score, explanations=explanations)

    @classmethod
    def encode_pair(cls, left: E, right: E) -> Encoded:
        """Encode the comparison between two entities as a set of feature values."""
        return [f(left, right) for f in cls.FEATURES]
