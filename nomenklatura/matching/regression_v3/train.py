import logging
import numpy as np
import multiprocessing
from typing import List, Tuple
from pprint import pprint
from numpy.typing import NDArray
from sklearn.pipeline import make_pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore
from sklearn.model_selection import GroupShuffleSplit  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn import metrics  # type: ignore
from concurrent.futures import ProcessPoolExecutor

from nomenklatura.judgement import Judgement
from nomenklatura.matching.pairs import read_pairs, JudgedPair
from nomenklatura.matching.regression_v3.model import RegressionV3
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


def pair_convert(pair: JudgedPair) -> Tuple[List[float], int]:
    """Encode a pair of training data into features and target."""
    judgement = 1 if pair.judgement == Judgement.POSITIVE else 0
    features = RegressionV3.encode_pair(pair.left, pair.right)
    return features, judgement


def pairs_to_arrays(
    pairs: List[JudgedPair],
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


def train_matcher(pairs_file: PathLike, splits: int = 1) -> None:
    pairs = []
    for pair in read_pairs(pairs_file):
        if pair.judgement == Judgement.UNSURE:
            pair.judgement = Judgement.NEGATIVE
        pairs.append(pair)
    positive = len([p for p in pairs if p.judgement == Judgement.POSITIVE])
    negative = len([p for p in pairs if p.judgement == Judgement.NEGATIVE])
    log.info("Total pairs loaded: %d (%d pos/%d neg)", len(pairs), positive, negative)

    X, y = pairs_to_arrays(pairs)
    groups = [p.group for p in pairs]
    gss = GroupShuffleSplit(n_splits=splits, test_size=0.33)
    for split, (train_indices, test_indices) in enumerate(
        gss.split(X, y, groups=groups), 1
    ):
        X_train = [X[i] for i in train_indices]
        X_test = [X[i] for i in test_indices]
        y_train = [y[i] for i in train_indices]
        y_test = [y[i] for i in test_indices]

        print()
        log.info("Training model...(split %d)" % split)
        logreg = LogisticRegression(penalty="l2")
        pipe = make_pipeline(StandardScaler(), logreg)
        pipe.fit(X_train, y_train)
        coef = logreg.coef_[0]
        coefficients = {n.__name__: c for n, c in zip(RegressionV3.FEATURES, coef)}
        RegressionV3.save(pipe, coefficients)

        print("Coefficients:")
        pprint(coefficients)
        y_pred = pipe.predict(X_test)
        cnf_matrix = metrics.confusion_matrix(y_test, y_pred, normalize="all") * 100
        print("Confusion matrix (% of all):\n", cnf_matrix)
        print("Accuracy:", metrics.accuracy_score(y_test, y_pred))
        print("Precision:", metrics.precision_score(y_test, y_pred))
        print("Recall:", metrics.recall_score(y_test, y_pred))

        y_pred_proba = pipe.predict_proba(X_test)[::, 1]
        auc = metrics.roc_auc_score(y_test, y_pred_proba)
        print("Area under curve:", auc)
