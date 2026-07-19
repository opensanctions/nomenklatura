from nomenklatura.matching.regression_v1.names import family_name_match
from nomenklatura.matching.regression_v1.names import first_name_match
from nomenklatura.matching.regression_v1.names import name_levenshtein
from nomenklatura.matching.regression_v1.names import name_match
from nomenklatura.matching.regression_v1.names import name_numbers
from nomenklatura.matching.regression_v1.names import name_token_overlap

from ..factory import e


def test_name_similarity_orders_exact_typo_and_unrelated_names():
    query = e("Person", name="Vladimir Putin")
    exact = e("Person", name="Vladimir Putin")
    typo = e("Person", name="Vladimir Pulin")
    unrelated = e("Person", name="Saddam Hussein")

    assert name_match(query, exact) == 1.0
    assert name_match(query, typo) == 0.0
    assert name_levenshtein(query, exact) == 1.0
    assert name_levenshtein(query, exact) > name_levenshtein(query, typo)
    assert name_levenshtein(query, typo) > name_levenshtein(query, unrelated)


def test_structured_name_parts_require_overlap():
    query = e("Person", firstName="Hans", lastName="Friedrich")
    exact = e("Person", firstName="Hans", lastName="Friedrich")
    swapped = e("Person", firstName="Friedrich", lastName="Hans")
    missing = e("Person", name="Hans Friedrich")

    assert first_name_match(query, exact) == 1.0
    assert family_name_match(query, exact) == 1.0
    assert first_name_match(query, swapped) == 0.0
    assert family_name_match(query, swapped) == 0.0
    assert first_name_match(query, missing) == 0.0
    assert family_name_match(query, missing) == 0.0


def test_name_token_overlap_uses_the_smaller_name_as_denominator():
    query = e("Person", name="Vladimir Putin")

    assert name_token_overlap(query, e("Person", name="Vladimir Putin")) == 1.0
    assert name_token_overlap(query, e("Person", name="Vladimir Pulin")) == 0.5
    assert name_token_overlap(query, e("Person", name="Saddam Hussein")) == 0.0


def test_name_numbers_only_flag_conflicting_numbers():
    query = e("Vessel", name="Sea Pony 1")

    assert name_numbers(query, e("Vessel", name="Sea Pony 1")) == 0.0
    assert name_numbers(query, e("Vessel", name="Sea Pony 2")) == 1.0
    assert name_numbers(query, e("Vessel", name="Sea Pony")) == 0.0
