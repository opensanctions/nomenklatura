import logging
import multiprocessing
import random
from concurrent.futures import ProcessPoolExecutor
from pprint import pprint
from typing import Dict, Iterable, List, Tuple

import numpy as np
from followthemoney import registry, EntityProxy
from followthemoney.util import PathLike
from numpy.typing import NDArray
from sklearn import metrics  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn.model_selection import train_test_split  # type: ignore
from sklearn.pipeline import make_pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore

from nomenklatura.judgement import Judgement
from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.pairs import JudgedPair, read_pairs

log = logging.getLogger(__name__)


def pair_convert(pair: JudgedPair) -> Tuple[List[float], int]:
    """Encode a pair of training data into features and target."""
    judgement = 1 if pair.judgement == Judgement.POSITIVE else 0
    features = EntityResolveRegression.encode_pair(pair.left, pair.right)
    return features, judgement


def pairs_to_arrays(
    pairs: Iterable[JudgedPair],
) -> Tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Parallelize feature computation for training data"""
    xrows = []
    yrows = []
    threads = multiprocessing.cpu_count()
    log.info("Compute threads: %d", threads)
    with ProcessPoolExecutor(max_workers=threads) as executor:
        results = executor.map(pair_convert, pairs, chunksize=1000)
        for idx, (x, y) in enumerate(results):
            if idx > 0 and idx % 10000 == 0:
                log.info("Computing features: %s....", idx)
            xrows.append(x)
            yrows.append(y)

    return np.array(xrows), np.array(yrows)


def _entity_weight(entity: EntityProxy) -> float:
    """This weights up entities with more matchable properties, to push down the
    value of name-only matches."""
    weight = 0.0
    # types = set()
    for prop, _ in entity.itervalues():
        if prop.matchable:
            inc_weight = 0.2 if prop.type == registry.name else 1.0
            weight += inc_weight
            # types.add(prop.type)
    # if entity.schema.is_a("LegalEntity") and types == {registry.name}:
    #     weight = weight * 0.5
    return weight


def weighted_pair_sort(pairs: List[JudgedPair]) -> List[JudgedPair]:
    for pair in pairs:
        left_weight = _entity_weight(pair.left)
        right_weight = _entity_weight(pair.right)
        # pair.weight = (left_weight + right_weight) / 2.0
        pair.weight = min(left_weight, right_weight)
    return sorted(pairs, key=lambda p: -p.weight)


def build_dataset(
    pairs_file: PathLike,
) -> Tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Load and balance a dataset from a JSON file."""
    pairs: List[JudgedPair] = []
    for pair in read_pairs(pairs_file):
        if not pair.left.schema.matchable or not pair.right.schema.matchable:
            continue
        if pair.left.schema.is_a("Address") or pair.right.schema.is_a("Address"):
            continue
        if pair.judgement == Judgement.UNSURE:
            pair.judgement = Judgement.NEGATIVE
        pairs.append(pair)
    positive = [p for p in pairs if p.judgement == Judgement.POSITIVE]
    negative = [p for p in pairs if p.judgement == Judgement.NEGATIVE]
    log.info(
        "Total pairs loaded: %d (%d pos/%d neg)",
        len(pairs),
        len(positive),
        len(negative),
    )
    # min_class = min(len(positive), len(negative))
    # log.info("Downsampling to %d per class", min_class)
    # if len(positive) > min_class:
    #     # positive = weighted_pair_sort(positive)
    #     pairs = positive[:min_class] + negative
    # else:
    #     # negative = weighted_pair_sort(negative)
    #     pairs = positive + negative[:min_class]
    random.shuffle(pairs)
    # log.info("Training pairs after downsampling: %d", len(pairs))
    schemata: Dict[str, int] = {}
    for pair in pairs:
        schemata[pair.schema.name] = schemata.get(pair.schema.name, 0) + 1
    log.info("Schemata distribution: %r", schemata)
    return pairs_to_arrays(pairs)


def train_matcher(pairs_file: PathLike) -> None:
    X, y = build_dataset(pairs_file)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.30)
    # logreg = LogisticRegression(class_weight={0: 95, 1: 1})
    # logreg = LogisticRegression(penalty="l1", solver="liblinear")
    logreg = LogisticRegression(penalty="l2")
    log.info("Training model...")
    pipe = make_pipeline(StandardScaler(), logreg)
    pipe.fit(X_train, y_train)
    coef = logreg.coef_[0]
    coefficients = {
        n.__name__: c for n, c in zip(EntityResolveRegression.FEATURES, coef)
    }
    EntityResolveRegression.save(pipe, coefficients)
    print("Written to: %s" % EntityResolveRegression.MODEL_PATH.as_posix())
    print("Coefficients:")
    pprint(coefficients)
    y_pred = pipe.predict(X_test)
    cnf_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("Confusion matrix:\n", cnf_matrix)
    print("Accuracy:", metrics.accuracy_score(y_test, y_pred))
    print("Precision:", metrics.precision_score(y_test, y_pred))
    print("Recall:", metrics.recall_score(y_test, y_pred))

    y_pred_proba = pipe.predict_proba(X_test)[::, 1]
    auc = metrics.roc_auc_score(y_test, y_pred_proba)
    print("Area under curve:", auc)
