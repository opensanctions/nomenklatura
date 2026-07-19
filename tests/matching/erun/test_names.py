from nomenklatura.matching.erun.names import family_name_match
from nomenklatura.matching.erun.names import legal_name_levenshtein
from nomenklatura.matching.erun.names import name_numbers
from nomenklatura.matching.erun.names import name_token_overlap
from nomenklatura.matching.erun.names import obj_name_levenshtein
from nomenklatura.matching.erun.names import org_name_levenshtein
from nomenklatura.matching.erun.names import person_name_levenshtein

from ..factory import e


def test_person_name_similarity_orders_exact_typo_and_unrelated_names():
    query = e("Person", name="Vladimir Putin")
    exact = e("Person", name="Vladimir Putin")
    typo = e("Person", name="Vladimir Pulin")
    unrelated = e("Person", name="Saddam Hussein")

    assert person_name_levenshtein(query, exact) == 1.0
    assert person_name_levenshtein(query, exact) > person_name_levenshtein(query, typo)
    assert person_name_levenshtein(query, typo) > person_name_levenshtein(
        query, unrelated
    )
    assert person_name_levenshtein(e("Company", name="Acme"), e("Company", name="Acme")) == 0.0


def test_organization_and_legal_entity_name_features_obey_schema_gates():
    full = e("Company", name="Siemens Aktiengesellschaft")
    short = e("Company", name="Siemens AG")

    assert org_name_levenshtein(full, short) == 1.0
    assert legal_name_levenshtein(full, short) == 0.0
    assert legal_name_levenshtein(
        e("LegalEntity", name="Acme"), e("LegalEntity", name="Acme")
    ) == 1.0
    assert org_name_levenshtein(e("Person", name="Acme"), e("Person", name="Acme")) == 0.0


def test_family_name_match_distinguishes_agreement_conflict_and_missingness():
    query = e("Person", lastName="Smith")

    assert family_name_match(query, e("Person", lastName="Smith")) == 1.0
    assert family_name_match(query, e("Person", lastName="Jones")) == -1.0
    assert family_name_match(query, e("Person")) == 0.0
    assert family_name_match(e("Company", name="Smith"), e("Company", name="Smith")) == 0.0


def test_name_token_and_number_features_keep_distinct_signals():
    query = e("Vessel", name="Sea Pony 1")

    assert name_token_overlap(query, e("Vessel", name="Sea Pony 1")) == 1.0
    assert name_token_overlap(query, e("Vessel", name="Sea Poni 1")) == 0.5
    assert name_numbers(query, e("Vessel", name="Sea Pony 1")) == 0.5
    assert name_numbers(query, e("Vessel", name="Sea Pony 2")) == -1.0
    assert name_numbers(query, e("Vessel", name="Sea Pony")) == 0.0


def test_object_name_similarity_is_strict_and_schema_limited():
    query = e("Vessel", name="Sea Pony")
    exact = e("Vessel", name="Sea Pony")
    typo = e("Vessel", name="Sea Poni")
    unrelated = e("Vessel", name="Blue Ocean")

    assert obj_name_levenshtein(query, exact) == 1.0
    assert obj_name_levenshtein(query, exact) > obj_name_levenshtein(query, typo)
    assert obj_name_levenshtein(query, typo) > obj_name_levenshtein(query, unrelated)
    assert obj_name_levenshtein(e("Company", name="Acme"), e("Company", name="Acme")) == 0.0
