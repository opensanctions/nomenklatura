from nomenklatura.matching.regression_v1.misc import address_match
from nomenklatura.matching.regression_v1.misc import address_numbers
from nomenklatura.matching.regression_v1.misc import birth_place
from nomenklatura.matching.regression_v1.misc import country_mismatch
from nomenklatura.matching.regression_v1.misc import email_match
from nomenklatura.matching.regression_v1.misc import gender_mismatch
from nomenklatura.matching.regression_v1.misc import identifier_match
from nomenklatura.matching.regression_v1.misc import org_identifier_match
from nomenklatura.matching.regression_v1.misc import phone_match

from ..factory import e


def test_birth_place_uses_normalized_token_overlap():
    query = e("Person", birthPlace="Berlin Germany")

    assert birth_place(query, e("Person", birthPlace="Berlin Germany")) == 1.0
    assert birth_place(query, e("Person", birthPlace="Berlin")) == 0.5
    assert birth_place(query, e("Person", birthPlace="Paris France")) == 0.0
    assert birth_place(query, e("Person")) == 0.0


def test_address_features_separate_text_and_number_evidence():
    query = e("Company", address="12 Main Street, Berlin")
    exact = e("Company", address="12 Main Street, Berlin")
    different = e("Company", address="34 Other Road, Paris")
    no_number = e("Company", address="Main Street, Berlin")

    assert address_match(query, exact) == 1.0
    assert address_match(query, exact) > address_match(query, different)
    assert address_numbers(query, exact) == 1.0
    assert address_numbers(query, different) == -1.0
    assert address_numbers(query, no_number) == 0.0
    assert address_numbers(no_number, query) == 0.0


def test_contact_features_require_a_matching_value():
    query = e("Person", phone="+49 30 1234", email="alice@example.com")
    same = e("Person", phone="+49 30 1234", email="alice@example.com")
    different = e("Person", phone="+49 30 9876", email="bob@example.com")
    missing = e("Person")

    assert phone_match(query, same) == 1.0
    assert email_match(query, same) == 1.0
    assert phone_match(query, different) == 0.0
    assert email_match(query, different) == 0.0
    assert phone_match(query, missing) == 0.0
    assert email_match(query, missing) == 0.0


def test_identifier_features_are_partitioned_by_entity_type():
    person = e("Person", passportNumber="C01X0001")
    same_person = e("Person", passportNumber="C01X0001")
    company = e("Company", registrationNumber="77401103")
    same_company = e("Company", registrationNumber="77401103")

    assert identifier_match(person, same_person) == 1.0
    assert org_identifier_match(person, same_person) == 0.0
    assert identifier_match(company, same_company) == 0.0
    assert org_identifier_match(company, same_company) == 1.0
    assert identifier_match(person, e("Person", passportNumber="C01X0002")) == 0.0


def test_gender_and_country_only_flag_present_conflicts():
    query = e("Person", gender="male", country="de")
    same = e("Person", gender="male", country="de")
    different = e("Person", gender="female", country="fr")
    missing = e("Person")

    assert gender_mismatch(query, same) == 0.0
    assert country_mismatch(query, same) == 0.0
    assert gender_mismatch(query, different) == 1.0
    assert country_mismatch(query, different) == 1.0
    assert gender_mismatch(query, missing) == 0.0
    assert country_mismatch(query, missing) == 0.0
