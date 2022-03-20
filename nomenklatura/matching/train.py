import json
import click
import pickle
import random
import logging
import numpy as np
from typing import Dict, List
from pprint import pprint
from followthemoney import model
from followthemoney.dedupe import Judgement
from nomenklatura.entity import CompositeEntity
from nomenklatura.matching.pairs import JudgedPair
from nomenklatura.matching.features import FEATURES

from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn import metrics


log = logging.getLogger(__name__)


def apply_predicates(left: CompositeEntity, right: CompositeEntity) -> Dict[str, float]:
    scores = {}
    for func in FEATURES:
        scores[func.__name__] = func(left, right)
    return scores


def pairs_to_arrays(pairs: List[JudgedPair]):
    xrows = []
    yrows = []
    for idx, pair in enumerate(pairs):
        if idx > 0 and idx % 10000 == 0:
            print("computing features: %s...." % idx)
        preds = apply_predicates(pair.left, pair.right)
        xvals = list(preds.values())
        xrows.append(xvals)

        yval = 0
        if pair.judgement == Judgement.POSITIVE:
            yval = 1
        yrows.append(yval)
    return np.array(xrows), np.array(yrows)


def read_pairs(pairs_file):
    pairs = []
    with open(pairs_file, "r") as fh:
        while line := fh.readline():
            data = json.loads(line)
            left_entity = CompositeEntity.from_dict(model, data["left"])
            right_entity = CompositeEntity.from_dict(model, data["right"])
            judgement = Judgement(data["judgement"])
            if judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
                continue
            if not left_entity.schema.is_a("LegalEntity"):
                continue
            pair = JudgedPair[CompositeEntity](left_entity, right_entity, judgement)
            pairs.append(pair)
    random.shuffle(pairs)
    return pairs


@click.command()
@click.argument("pairs_file", type=click.Path(exists=True, file_okay=True))
def train_matcher(pairs_file):
    pairs = read_pairs(pairs_file)
    print("total pairs", len(pairs))
    print("positive", len([p for p in pairs if p.judgement == Judgement.POSITIVE]))
    print("negative", len([p for p in pairs if p.judgement == Judgement.NEGATIVE]))
    X, y = pairs_to_arrays(pairs)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.33)
    print("built training data")
    # based on: https://www.datacamp.com/community/tutorials/understanding-logistic-regression-python
    logreg = LogisticRegression(class_weight={0: 0.95, 1: 0.05})
    print("training model...")
    pipe = make_pipeline(StandardScaler(), logreg)
    pipe.fit(X_train, y_train)
    coef = logreg.coef_[0]
    coef_named = {n.__name__: c for n, c in zip(FEATURES, coef)}
    print("Coefficients:")
    pprint(coef_named)

    y_pred = pipe.predict(X_test)
    cnf_matrix = metrics.confusion_matrix(y_test, y_pred)
    print("Confusion matrix:\n", cnf_matrix)
    print("Accuracy:", metrics.accuracy_score(y_test, y_pred))
    print("Precision:", metrics.precision_score(y_test, y_pred))
    print("Recall:", metrics.recall_score(y_test, y_pred))

    y_pred_proba = pipe.predict_proba(X_test)[::, 1]
    auc = metrics.roc_auc_score(y_test, y_pred_proba)
    print("AUC:", auc)

    mdl = pickle.dumps(pipe)
    with open("nkmatch.pkl", "wb") as fh:
        fh.write(mdl)

    use_matcher()


def compare(left, right):
    with open("nkmatch.pkl", "rb") as fh:
        pipe = pickle.loads(fh.read())

    features = apply_predicates(left, right)
    npfeat = np.array([list(features.values())])
    pred = pipe.predict_proba(npfeat)
    print("-----------------")
    print(left, right)
    print(npfeat)
    print(pred)


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
    entity1 = CompositeEntity.from_data(model, data1, [])
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
    entity2 = CompositeEntity.from_data(model, data2, [])
    compare(entity1, entity2)

    data2 = {
        "id": "right-putin",
        "schema": "Person",
        "properties": {
            "name": ["Vladimir Vladimirovich Putin"],
            "birthDate": ["1952-10-07"],
        },
    }
    entity2 = CompositeEntity.from_data(model, data2, [])
    compare(entity1, entity2)

    data3 = {
        "id": "other-guy",
        "schema": "Person",
        "properties": {
            "name": ["Saddam Hussein"],
            "birthDate": ["1937-04-28"],
        },
    }
    entity3 = CompositeEntity.from_data(model, data3, [])
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
    entity4 = CompositeEntity.from_data(model, data4, [])
    compare(entity1, entity4)


if __name__ == "__main__":
    # configure_logging()
    logging.basicConfig(level=logging.INFO)
    train_matcher()
    # use_matcher()
