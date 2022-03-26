from base64 import encode
import click
import logging
import numpy as np
import multiprocessing
from typing import Dict, Iterable
from pprint import pprint
from followthemoney import model
from followthemoney.dedupe import Judgement
from concurrent.futures import ThreadPoolExecutor
from nomenklatura.entity import CompositeEntity
from nomenklatura.matching.pairs import read_pairs, JudgedPair
from nomenklatura.matching.features import FEATURES, encode_pair
from nomenklatura.matching.model import explain_matcher, save_matcher, compare_scored

from sklearn.pipeline import make_pipeline  # type: ignore
from sklearn.preprocessing import StandardScaler  # type: ignore
from sklearn.model_selection import train_test_split  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn import metrics  # type: ignore


log = logging.getLogger(__name__)


# def randomize_entity(entity: CompositeEntity):
#     if entity.has("firstName", quiet=True) and entity.has("lastName", quiet=True):
#         rand = random.randint(0, 10)
#         if rand < 3:
#             entity.pop("name", quiet=True)
#             entity.pop("alias", quiet=True)


# def apply_predicates(left: CompositeEntity, right: CompositeEntity) -> Dict[str, float]:
#     scores = {}
#     for func in FEATURES:
#         scores[func.__name__] = func(left, right)
#     return scores


def pair_convert(pair: JudgedPair):
    judgement = 1 if pair.judgement == Judgement.POSITIVE else 0
    features = encode_pair(pair.left, pair.right)
    return features, judgement


def pairs_to_arrays(pairs: Iterable[JudgedPair]):
    xrows = []
    yrows = []
    threads = multiprocessing.cpu_count()
    print("compute threads", threads)
    with ThreadPoolExecutor(max_workers=threads) as excecutor:
        results = excecutor.map(pair_convert, pairs)
        for idx, (x, y) in enumerate(results):
            if idx > 0 and idx % 10000 == 0:
                print("computing features: %s...." % idx)
            xrows.append(x)
            yrows.append(y)

    return np.array(xrows), np.array(yrows)


@click.command()
@click.argument("pairs_file", type=click.Path(exists=True, file_okay=True))
def train_matcher(pairs_file):
    pairs = []
    for pair in read_pairs(pairs_file):
        # HACK: support more eventually:
        if not pair.left.schema.is_a("LegalEntity"):
            continue
        # randomize_entity(pair.left)
        # randomize_entity(pair.right)
        pairs.append(pair)
    # random.shuffle(pairs)
    # pairs = pairs[:30000]
    print("total pairs", len(pairs))
    # print("positive", len([p for p in pairs if p.judgement == Judgement.POSITIVE]))
    # print("negative", len([p for p in pairs if p.judgement == Judgement.NEGATIVE]))
    X, y = pairs_to_arrays(pairs)
    print("built data")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.33)
    print("computed test/train split")
    # based on: https://www.datacamp.com/community/tutorials/understanding-logistic-regression-python
    # logreg = LogisticRegression(class_weight={0: 95, 1: 1})
    # logreg = LogisticRegression(penalty="l1", solver="liblinear")
    logreg = LogisticRegression(penalty="l2")
    print("training model...")
    pipe = make_pipeline(StandardScaler(), logreg)
    pipe.fit(X_train, y_train)
    coef = logreg.coef_[0]
    coefficients = {n.__name__: c for n, c in zip(FEATURES, coef)}
    print("Coefficients:")
    pprint(coefficients)
    save_matcher(pipe, coefficients)

    y_pred = pipe.predict(X_test)
    cnf_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("Confusion matrix:\n", cnf_matrix)
    print("Accuracy:", metrics.accuracy_score(y_test, y_pred))
    print("Precision:", metrics.precision_score(y_test, y_pred))
    print("Recall:", metrics.recall_score(y_test, y_pred))

    y_pred_proba = pipe.predict_proba(X_test)[::, 1]
    auc = metrics.roc_auc_score(y_test, y_pred_proba)
    print("AUC:", auc)

    use_matcher()


def compare(left, right):
    print("---------------------------")
    print(repr(left), repr(right))
    score, features = compare_scored(left, right)
    print("Score: ", score)
    print("Features: ")
    pprint(features)


# @click.command()
def use_matcher():
    data1 = {
        "id": "left-putin",
        "schema": "Person",
        "properties": {
            "name": ["Vladimir Putin"],
            "birthDate": ["1952-10-07"],
            "country": ["ru"],
        },
    }
    entity1 = CompositeEntity.from_data(model, data1, {})
    compare(entity1, entity1)

    data2 = {
        "id": "right-putin",
        "schema": "Person",
        "properties": {
            "name": ["Vladimir Vladimirovich Putin"],
            "birthDate": ["1952-10-07"],
            "nationality": ["ru"],
        },
    }
    entity2 = CompositeEntity.from_data(model, data2, {})
    compare(entity1, entity2)

    data2 = {
        "id": "right-putin",
        "schema": "Person",
        "properties": {
            "name": ["Vladimir Vladimirovich Putin"],
            "birthDate": ["1952-10-07"],
        },
    }
    entity2 = CompositeEntity.from_data(model, data2, {})
    compare(entity1, entity2)

    data3 = {
        "id": "other-guy",
        "schema": "Person",
        "properties": {
            "name": ["Saddam Hussein"],
            "birthDate": ["1937-04-28"],
        },
    }
    entity3 = CompositeEntity.from_data(model, data3, {})
    compare(entity1, entity3)

    data4 = {
        "id": "other-guy",
        "schema": "Person",
        "properties": {
            "name": ["Saddam Hussein"],
            "birthDate": ["1937"],
            "nationality": ["iq"],
        },
    }
    entity4 = CompositeEntity.from_data(model, data4, {})
    compare(entity1, entity4)


if __name__ == "__main__":
    # configure_logging()
    logging.basicConfig(level=logging.INFO)
    # train_matcher()
    pprint(explain_matcher())
    use_matcher()
