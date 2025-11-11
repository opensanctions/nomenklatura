import pickle
import numpy as np
from typing import List, Dict, Tuple, cast
from functools import cache
from sklearn.pipeline import Pipeline  # type: ignore
from followthemoney import E

from nomenklatura.matching.erun.names import name_levenshtein, family_name_match
from nomenklatura.matching.erun.names import name_token_overlap, name_numbers
from nomenklatura.matching.erun.names import obj_name_levenshtein
from nomenklatura.matching.erun.misc import address_match, address_numbers
from nomenklatura.matching.erun.misc import birth_place, gender_mismatch
from nomenklatura.matching.erun.misc import contact_match
from nomenklatura.matching.erun.misc import security_isin_match
from nomenklatura.matching.erun.countries import (
    org_obj_country_match,
    per_country_mismatch,
    pos_country_mismatch,
)
from nomenklatura.matching.erun.identifiers import strong_identifier_match
from nomenklatura.matching.erun.identifiers import weak_identifier_match
from nomenklatura.matching.compare.dates import dob_matches, dob_year_matches
from nomenklatura.matching.compare.dates import dob_year_disjoint
from nomenklatura.matching.types import (
    FeatureDocs,
    FeatureDoc,
    MatchingResult,
    ScoringConfig,
)
from nomenklatura.matching.types import CompareFunction, FtResult
from nomenklatura.matching.types import Encoded, ScoringAlgorithm
from nomenklatura.matching.util import make_github_url
from nomenklatura.util import DATA_PATH


class EntityResolveRegression(ScoringAlgorithm):
    """Entity resolution matcher. Do not use this in (regulated) screening scenarios."""

    NAME = "er-unstable"
    MODEL_PATH = DATA_PATH.joinpath(f"{NAME}.pkl")
    FEATURES: List[CompareFunction] = [
        name_token_overlap,
        name_numbers,
        name_levenshtein,
        strong_identifier_match,
        weak_identifier_match,
        dob_matches,
        dob_year_matches,
        contact_match,
        FtResult.unwrap(dob_year_disjoint),
        family_name_match,
        birth_place,
        gender_mismatch,
        per_country_mismatch,
        org_obj_country_match,
        pos_country_mismatch,
        security_isin_match,
        obj_name_levenshtein,
        address_match,
        address_numbers,
    ]

    @classmethod
    def save(cls, pipe: Pipeline, coefficients: Dict[str, float]) -> None:
        """Store a classification pipeline after training."""
        mdl = pickle.dumps({"pipe": pipe, "coefficients": coefficients})
        with open(cls.MODEL_PATH, "wb") as fh:
            fh.write(mdl)
        cls.load.cache_clear()

    @classmethod
    @cache
    def load(cls) -> Tuple[Pipeline, Dict[str, float]]:
        """Load a pre-trained classification pipeline for ad-hoc use."""
        with open(cls.MODEL_PATH, "rb") as fh:
            matcher = pickle.loads(fh.read())
        pipe = cast(Pipeline, matcher["pipe"])
        coefficients = cast(Dict[str, float], matcher["coefficients"])
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
        score = cast(float, pred[0][1])
        explanations: Dict[str, FtResult] = {}
        for feature, coeff in zip(cls.FEATURES, encoded):
            name = feature.__name__
            explanations[name] = FtResult(score=float(coeff), detail=None)
        return MatchingResult.make(score=score, explanations=explanations)

    @classmethod
    def encode_pair(cls, left: E, right: E) -> Encoded:
        """Encode the comparison between two entities as a set of feature values."""
        return [f(left, right) for f in cls.FEATURES]
