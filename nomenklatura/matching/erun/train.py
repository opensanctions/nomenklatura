import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pprint import pprint
from typing import Dict, Iterable, List, Tuple

import numpy as np
from followthemoney.util import PathLike
from numpy.typing import NDArray
from sklearn import metrics  # type: ignore
from sklearn.linear_model import LogisticRegressionCV  # type: ignore
from sklearn.model_selection import train_test_split  # type: ignore
from sklearn.pipeline import make_pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore

from nomenklatura.judgement import Judgement
from nomenklatura.matching.erun.model import EntityResolveRegression
from nomenklatura.matching.pairs import JudgedPair, read_pairs

log = logging.getLogger(__name__)

RANDOM_SEED = 42


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


def build_dataset(
    pairs_file: PathLike,
) -> Tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Load a dataset from a JSON file.

    All judged pairs are kept (no downsampling): the model is trained and
    calibrated on the real, imbalanced class distribution.
    """
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
    schemata: Dict[str, int] = {}
    for pair in pairs:
        schemata[pair.schema.name] = schemata.get(pair.schema.name, 0) + 1
    log.info("Schemata distribution: %r", schemata)
    return pairs_to_arrays(pairs)


def train_matcher(pairs_file: PathLike) -> None:
    X, y = build_dataset(pairs_file)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.30, random_state=RANDOM_SEED, stratify=y
    )
    # Cross-validate both the regularization strength (C) and the L1/L2 mix
    # (l1_ratio). The grid spans pure L2 (0.0) through pure L1 (1.0), so CV
    # decides the penalty type rather than us guessing it. Probabilities are
    # used directly as match scores, so select on log loss (calibration), not
    # accuracy. No class_weight: re-weighting to balanced calibrates for a 50/50
    # prior and miscalibrates probabilities on the real (imbalanced) distribution.
    logreg = LogisticRegressionCV(
        Cs=10,
        l1_ratios=[0.0, 0.25, 0.5, 0.75, 1.0],
        solver="saga",
        scoring="neg_log_loss",
        cv=5,
        max_iter=2000,
        random_state=RANDOM_SEED,
        n_jobs=-1,
        use_legacy_attributes=False,
    )
    log.info("Training model (cross-validating C and l1_ratio)...")
    pipe = make_pipeline(StandardScaler(with_mean=False), logreg)
    pipe.fit(X_train, y_train)
    log.info(
        "Selected C=%.4f, l1_ratio=%.2f", logreg.C_, logreg.l1_ratio_
    )
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
