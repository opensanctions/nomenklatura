import pickle
from functools import cache
from nomenklatura.util import DATA_PATH
from sklearn.pipeline import Pipeline  # type: ignore

MODEL_PATH = DATA_PATH.joinpath("match-regression.pkl")

# TODO: put in a feature list so we can detect if the set
# has changed and a new model needs to be built.


def save_matcher(pipe: Pipeline) -> None:
    """Store a classification pipeline after training."""
    mdl = pickle.dumps(pipe)
    with open(MODEL_PATH, "wb") as fh:
        fh.write(mdl)
    load_matcher.cache_clear()


@cache
def load_matcher() -> Pipeline:
    """Load a pre-trained classification pipeline for ad-hoc use."""
    with open(MODEL_PATH, "rb") as fh:
        return pickle.loads(fh.read())
