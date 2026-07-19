from nomenklatura.matching.erun.identifiers import strong_identifier_match
from nomenklatura.matching.erun.identifiers import weak_identifier_match

from ..factory import e


LEI = "1595VL9OPPQ5THEK2X30"
OTHER_LEI = "529900T8BM49AURSDO55"


def test_strong_identifier_match_distinguishes_matches_and_conflicts():
    query = e("Company", leiCode=LEI)

    assert strong_identifier_match(query, e("Company", leiCode=LEI)) == 1.0
    assert strong_identifier_match(query, e("Company", leiCode=OTHER_LEI)) == -0.2
    assert strong_identifier_match(query, e("Company")) == 0.0


def test_strong_identifier_match_falls_back_to_weak_identifiers():
    strong = e("Company", leiCode=LEI)
    weak = e("Company", registrationNumber=LEI)
    unrelated = e("Company", registrationNumber="77401103")

    assert strong_identifier_match(strong, weak) == 0.7
    assert strong_identifier_match(weak, strong) == 0.7
    assert strong_identifier_match(strong, unrelated) == 0.0
    assert strong_identifier_match(unrelated, strong) == 0.0


def test_weak_identifier_match_requires_legal_entities():
    query = e("Company", registrationNumber="77401103")

    assert weak_identifier_match(query, e("Company", registrationNumber="77401103")) == 1.0
    assert weak_identifier_match(query, e("Company", registrationNumber="77401104")) == 0.0
    assert weak_identifier_match(query, e("Company")) == 0.0
    assert weak_identifier_match(
        e("Person", idNumber="77401103"), e("Person", idNumber="77401103")
    ) == 1.0
    assert weak_identifier_match(
        e("Address", remarks="77401103"), e("Address", remarks="77401103")
    ) == 0.0
