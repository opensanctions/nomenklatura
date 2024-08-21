import logging
import numpy as np
import multiprocessing
from typing import Iterable, List, Tuple
from pprint import pprint
from numpy.typing import NDArray
from sklearn.pipeline import make_pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore
from sklearn.model_selection import train_test_split  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn import metrics  # type: ignore
from concurrent.futures import ThreadPoolExecutor

from nomenklatura.judgement import Judgement
from nomenklatura.matching.pairs import read_pair_sets, JudgedPair
from nomenklatura.matching.regression_v3.model import RegressionV3
from nomenklatura.util import PathLike

log = logging.getLogger(__name__)


def pair_convert(pair: JudgedPair) -> Tuple[List[float], int]:
    """Encode a pair of training data into features and target."""
    judgement = 1 if pair.judgement == Judgement.POSITIVE else 0
    features = RegressionV3.encode_pair(pair.left, pair.right)
    return features, judgement


def pairs_to_arrays(
    pairs: Iterable[JudgedPair],
) -> Tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Parallelize feature computation for training data"""
    xrows = []
    yrows = []
    threads = multiprocessing.cpu_count()
    log.info("Compute threads: %d", threads)
    with ThreadPoolExecutor(max_workers=threads) as excecutor:
        results = excecutor.map(pair_convert, pairs)
        for idx, (x, y) in enumerate(results):
            if idx > 0 and idx % 10000 == 0:
                log.info("Computing features: %s....", idx)
            xrows.append(x)
            yrows.append(y)

    return np.array(xrows), np.array(yrows)


def train_matcher(pairs_file: PathLike) -> None:
    pair_sets = read_pair_sets(pairs_file)
    
    positive = sum([len([p for p in s if p.judgement == Judgement.POSITIVE]) for s in pair_sets])
    negative = sum([len([p for p in s if p.judgement == Judgement.NEGATIVE]) for s in pair_sets])

    log.info("Total pairs loaded: %d (%d pos/%d neg)", positive+negative, positive, negative)
    log.info("Total independent sets loaded: %d", len(pair_sets))

    train_sets, test_sets = train_test_split(pair_sets, test_size=0.33)
    log.info("Training sets: %d, Test sets: %d - test is %d%%", len(train_sets), len(test_sets), 100*len(test_sets)/(len(pair_sets)))
    train_pairs = [p for s in train_sets for p in s]
    test_pairs = [p for s in test_sets for p in s]
    log.info("Training pairs: %d, Test pairs: %d, test is %d%%", len(train_pairs), len(test_pairs), 100*len(test_pairs)/(len(train_pairs)+len(test_pairs)))

    X_train, y_train = pairs_to_arrays(train_pairs)
    X_test, y_test = pairs_to_arrays(test_pairs)

    # logreg = LogisticRegression(class_weight={0: 95, 1: 1})
    # logreg = LogisticRegression(penalty="l1", solver="liblinear")
    logreg = LogisticRegression(penalty="l2")
    log.info("Training model...")
    pipe = make_pipeline(StandardScaler(), logreg)
    pipe.fit(X_train, y_train)
    coef = logreg.coef_[0]
    coefficients = {n.__name__: c for n, c in zip(RegressionV3.FEATURES, coef)}
    RegressionV3.save(pipe, coefficients)
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
