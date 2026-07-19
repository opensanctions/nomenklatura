import numpy as np

from nomenklatura.judgement import Judgement
from nomenklatura.matching.pairs import JudgedPair
from nomenklatura.matching.regression_v1.model import RegressionV1
from nomenklatura.matching.regression_v1.train import pair_convert, pairs_to_arrays

from ..factory import e


def make_pair(judgement: Judgement, left_name: str, right_name: str) -> JudgedPair:
    left = e("Person", name=left_name)
    right = e("Person", name=right_name)
    return JudgedPair(left, right, judgement)


def test_pair_convert_maps_judgements_and_features():
    positive = make_pair(Judgement.POSITIVE, "Vladimir Putin", "Vladimir Putin")
    negative = make_pair(Judgement.NEGATIVE, "Vladimir Putin", "Saddam Hussein")

    positive_features, positive_label = pair_convert(positive)
    negative_features, negative_label = pair_convert(negative)

    assert positive_label == 1
    assert negative_label == 0
    assert positive_features == RegressionV1.encode_pair(positive.left, positive.right)
    assert negative_features == RegressionV1.encode_pair(negative.left, negative.right)


def test_pairs_to_arrays_preserves_input_order_and_shape():
    pairs = [
        make_pair(Judgement.POSITIVE, "Vladimir Putin", "Vladimir Putin"),
        make_pair(Judgement.NEGATIVE, "Vladimir Putin", "Saddam Hussein"),
    ]

    features, labels = pairs_to_arrays(pairs)

    assert features.shape == (2, len(RegressionV1.FEATURES))
    assert labels.tolist() == [1, 0]
    assert np.isfinite(features).all()
    assert features[0].tolist() == RegressionV1.encode_pair(
        pairs[0].left, pairs[0].right
    )
