from banal import ensure_list
from followthemoney import EntityProxy

from nomenklatura.matching.erun.misc import (
    address_match,
    address_number_disagreement,
    address_number_overlap,
    birth_place,
    contact_match,
    gender_mismatch,
    security_isin_mismatch,
)


def entity(*addresses: str) -> EntityProxy:
    return EntityProxy.from_dict(
        {
            "id": "entity",
            "schema": "Company",
            "properties": {"address": ensure_list(addresses)},
        }
    )


def test_address_number_features_are_symmetric_and_bounded() -> None:
    left = entity("12 Main Street", "34 Second Street")
    right = entity("Main Street 12")

    assert address_number_overlap(left, right) == 1.0
    assert address_number_overlap(right, left) == 1.0
    assert address_number_disagreement(left, right) == 0.5
    assert address_number_disagreement(right, left) == 0.5


def test_address_number_features_separate_disagreement_and_missingness() -> None:
    left = entity("12 Main Street")
    different = entity("34 Main Street")
    missing = entity("Main Street")

    assert address_number_overlap(left, different) == 0.0
    assert address_number_disagreement(left, different) == 1.0
    assert address_number_overlap(left, missing) == 0.0
    assert address_number_disagreement(left, missing) == 0.0


def test_birth_place_and_address_match_use_normalized_tokens() -> None:
    person = EntityProxy.from_dict(
        {
            "id": "person",
            "schema": "Person",
            "properties": {"birthPlace": ["Berlin Germany"]},
        }
    )
    same_person = EntityProxy.from_dict(
        {
            "id": "same-person",
            "schema": "Person",
            "properties": {"birthPlace": ["Berlin"]},
        }
    )
    assert birth_place(person, same_person) == 1.0
    assert birth_place(person, EntityProxy.from_dict({"id": "missing", "schema": "Person", "properties": {}})) == 0.0

    query = entity("12 Main Street, Berlin")
    partial = entity("Main Street, Berlin")
    unrelated = entity("34 Other Road, Paris")
    assert address_match(query, partial) == 1.0
    assert address_match(query, unrelated) == 0.0


def test_gender_mismatch_ignores_missing_and_other_values() -> None:
    male = EntityProxy.from_dict(
        {"id": "male", "schema": "Person", "properties": {"gender": ["male"]}}
    )
    female = EntityProxy.from_dict(
        {"id": "female", "schema": "Person", "properties": {"gender": ["female"]}}
    )
    other = EntityProxy.from_dict(
        {"id": "other", "schema": "Person", "properties": {"gender": ["other"]}}
    )
    missing = EntityProxy.from_dict(
        {"id": "missing-gender", "schema": "Person", "properties": {}}
    )

    assert gender_mismatch(male, female) == 1.0
    assert gender_mismatch(male, male) == 0.0
    assert gender_mismatch(male, other) == 0.0
    assert gender_mismatch(male, missing) == 0.0


def test_contact_match_checks_phone_email_then_url() -> None:
    phone = EntityProxy.from_dict(
        {"id": "phone", "schema": "Person", "properties": {"phone": ["+49 30 1234"]}}
    )
    email = EntityProxy.from_dict(
        {"id": "email", "schema": "Person", "properties": {"email": ["alice@example.com"]}}
    )
    website = EntityProxy.from_dict(
        {"id": "website", "schema": "Company", "properties": {"website": ["https://example.com"]}}
    )

    assert contact_match(phone, phone) == 1.0
    assert contact_match(email, email) == 1.0
    assert contact_match(website, website) == 1.0
    assert contact_match(phone, email) == 0.0


def test_security_isin_mismatch_requires_conflicting_security_codes() -> None:
    query = EntityProxy.from_dict(
        {"id": "security", "schema": "Security", "properties": {"isin": ["US0378331005"]}}
    )
    same = EntityProxy.from_dict(
        {"id": "same-security", "schema": "Security", "properties": {"isin": ["US0378331005"]}}
    )
    different = EntityProxy.from_dict(
        {"id": "other-security", "schema": "Security", "properties": {"isin": ["US5949181045"]}}
    )
    missing = EntityProxy.from_dict(
        {"id": "missing-isin", "schema": "Security", "properties": {}}
    )

    assert security_isin_mismatch(query, same) == 0.0
    assert security_isin_mismatch(query, different) == 1.0
    assert security_isin_mismatch(query, missing) == 0.0
    assert security_isin_mismatch(entity("US0378331005"), entity("US5949181045")) == 0.0
