import pickle
import numpy as np
from typing import List, Dict, Tuple, cast
from functools import cache
from sklearn.pipeline import Pipeline  # type: ignore
from followthemoney.proxy import E

from nomenklatura.matching.regression_v1.names import first_name_match
from nomenklatura.matching.regression_v1.names import family_name_match
from nomenklatura.matching.regression_v1.names import name_levenshtein, name_match
from nomenklatura.matching.regression_v1.names import name_token_overlap, name_numbers
from nomenklatura.matching.regression_v1.misc import phone_match, email_match
from nomenklatura.matching.regression_v1.misc import address_match, address_numbers
from nomenklatura.matching.regression_v1.misc import identifier_match, birth_place
from nomenklatura.matching.regression_v1.misc import org_identifier_match
from nomenklatura.matching.compare.countries import country_mismatch
from nomenklatura.matching.compare.gender import gender_mismatch
from nomenklatura.matching.compare.dates import dob_matches, dob_year_matches
from nomenklatura.matching.compare.dates import dob_year_disjoint
from nomenklatura.matching.types import FeatureDocs, FeatureDoc, MatchingResult
from nomenklatura.matching.types import CompareFunction, Encoded, ScoringAlgorithm
from nomenklatura.matching.util import make_github_url
from nomenklatura.util import DATA_PATH


class RegressionV1(ScoringAlgorithm):
    """A simple matching algorithm based on a regression model."""

    NAME = "regression-v1"
    MODEL_PATH = DATA_PATH.joinpath(f"{NAME}.pkl")
    FEATURES: List[CompareFunction] = [
        name_match,
        name_token_overlap,
        name_numbers,
        name_levenshtein,
        phone_match,
        email_match,
        identifier_match,
        dob_matches,
        dob_year_matches,
        dob_year_disjoint,
        first_name_match,
        family_name_match,
        birth_place,
        gender_mismatch,
        country_mismatch,
        org_identifier_match,
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
        cls.explain.cache_clear()

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
    @cache
    def explain(cls) -> FeatureDocs:
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
    def compare(
        cls, query: E, match: E, override_weights: Dict[str, float] = {}
    ) -> MatchingResult:
        """Use a regression model to compare two entities."""
        pipe, _ = cls.load()
        encoded = cls.encode_pair(query, match)
        npfeat = np.array([encoded])
        pred = pipe.predict_proba(npfeat)
        score = cast(float, pred[0][1])
        features = {f.__name__: float(c) for f, c in zip(cls.FEATURES, encoded)}
        return MatchingResult.make(score=score, features=features)

    @classmethod
    def encode_pair(cls, left: E, right: E) -> Encoded:
        """Encode the comparison between two entities as a set of feature values."""
        return [f(left, right) for f in cls.FEATURES]
