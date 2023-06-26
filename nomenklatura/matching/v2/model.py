import pickle
import numpy as np
from typing import List, Dict, Tuple, cast
from functools import cache
from nomenklatura.util import DATA_PATH
from sklearn.pipeline import Pipeline  # type: ignore
from followthemoney.proxy import E

from nomenklatura.matching.types import FeatureDocs, MatchingResult
from nomenklatura.matching.v2.dates import dob_matches, dob_year_matches
from nomenklatura.matching.v2.names import first_name_match, family_name_match
from nomenklatura.matching.v2.names import name_levenshtein
from nomenklatura.matching.v2.names import name_part_soundex, name_numbers
from nomenklatura.matching.v2.misc import address_match, address_numbers
from nomenklatura.matching.v2.misc import identifier_match, birth_place
from nomenklatura.matching.v2.misc import gender_mismatch, country_mismatch
from nomenklatura.matching.v2.misc import org_identifier_match
from nomenklatura.matching.util import make_github_url
from nomenklatura.matching.types import FeatureItem, Encoded, ScoringAlgorithm


class MatcherV2(ScoringAlgorithm):
    """A simple matching algorithm based on a regression model with phonetic comparison."""

    NAME = "regression-v2"
    MODEL_PATH = DATA_PATH.joinpath(f"{NAME}.pkl")
    FEATURES: List[FeatureItem] = [
        name_part_soundex,
        name_numbers,
        name_levenshtein,
        identifier_match,
        dob_matches,
        dob_year_matches,
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
            features[name] = {
                "description": func.__doc__,
                "coefficient": float(coefficients[name]),
                "url": make_github_url(func),
            }
        return features

    @classmethod
    def compare(cls, query: E, match: E) -> MatchingResult:
        """Use a regression model to compare two entities."""
        pipe, _ = cls.load()
        encoded = cls.encode_pair(query, match)
        npfeat = np.array([encoded])
        pred = pipe.predict_proba(npfeat)
        score = cast(float, pred[0][1])
        features = {f.__name__: float(c) for f, c in zip(cls.FEATURES, encoded)}
        return {"score": score, "features": features}

    @classmethod
    def encode_pair(cls, left: E, right: E) -> Encoded:
        """Encode the comparison between two entities as a set of feature values."""
        return [f(left, right) for f in cls.FEATURES]
