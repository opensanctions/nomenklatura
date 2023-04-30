import pickle
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, cast
from functools import cache
from nomenklatura.util import DATA_PATH
from sklearn.pipeline import Pipeline  # type: ignore

from nomenklatura import __version__
from nomenklatura.entity import CompositeEntity as Entity
from nomenklatura.matching.types import FeatureDocs, MatchingResult
from nomenklatura.matching.v1.dates import dob_matches, dob_year_matches
from nomenklatura.matching.v1.names import first_name_match, family_name_match
from nomenklatura.matching.v1.names import name_levenshtein, name_match
from nomenklatura.matching.v1.names import name_token_overlap, name_numbers
from nomenklatura.matching.v1.misc import phone_match, email_match
from nomenklatura.matching.v1.misc import address_match, address_numbers
from nomenklatura.matching.v1.misc import identifier_match, birth_place
from nomenklatura.matching.v1.misc import gender_mismatch, country_mismatch
from nomenklatura.matching.v1.misc import org_identifier_match
from nomenklatura.matching.types import FeatureItem

Encoded = List[float]
NAME = "regression-v1"
BASE_URL = "https://github.com/opensanctions/nomenklatura/blob/%s/nomenklatura/%s#L%s"
MODEL_PATH = DATA_PATH.joinpath(f"{NAME}.pkl")
CODE_PATH = DATA_PATH.joinpath("..").resolve()
FEATURES: List[FeatureItem] = [
    name_match,
    name_token_overlap,
    name_numbers,
    name_levenshtein,
    phone_match,
    email_match,
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


def save_matcher(pipe: Pipeline, coefficients: Dict[str, float]) -> None:
    """Store a classification pipeline after training."""
    mdl = pickle.dumps({"pipe": pipe, "coefficients": coefficients})
    with open(MODEL_PATH, "wb") as fh:
        fh.write(mdl)
    load_matcher.cache_clear()
    explain_matcher.cache_clear()


@cache
def load_matcher() -> Tuple[Pipeline, Dict[str, float]]:
    """Load a pre-trained classification pipeline for ad-hoc use."""
    with open(MODEL_PATH, "rb") as fh:
        matcher = pickle.loads(fh.read())
    pipe = cast(Pipeline, matcher["pipe"])
    coefficients = cast(Dict[str, float], matcher["coefficients"])
    current = [f.__name__ for f in FEATURES]
    if list(coefficients.keys()) != current:
        raise RuntimeError("Model was not trained on identical features!")
    return pipe, coefficients


@cache
def explain_matcher() -> FeatureDocs:
    """Return an explanation of the features and their coefficients."""
    features: FeatureDocs = {}
    _, coefficients = load_matcher()
    for func in FEATURES:
        name = func.__name__
        code_path = Path(func.__code__.co_filename).relative_to(CODE_PATH)
        line_no = func.__code__.co_firstlineno
        url = BASE_URL % (__version__, code_path, line_no)
        features[name] = {
            "description": func.__doc__,
            "coefficient": float(coefficients[name]),
            "url": url,
        }
    return features


def compare_scored(left: Entity, right: Entity) -> MatchingResult:
    """Encode a comparison of the two entities, apply the model and return a score."""
    pipe, _ = load_matcher()
    encoded = encode_pair(left, right)
    npfeat = np.array([encoded])
    pred = pipe.predict_proba(npfeat)
    score = cast(float, pred[0][1])
    features = {f.__name__: float(c) for f, c in zip(FEATURES, encoded)}
    return {"score": score, "features": features}


def encode_pair(left: Entity, right: Entity) -> Encoded:
    """Encode the comparison between two entities as a set of feature values."""
    return [f(left, right) for f in FEATURES]
