from nomenklatura.matching.erun.countries import org_country_mismatch
from nomenklatura.matching.erun.countries import per_country_mismatch
from nomenklatura.matching.erun.countries import position_country_match

from ..factory import e


def test_position_country_match_requires_country_evidence_on_positions():
    query = e("Position", country="de")

    assert position_country_match(query, e("Position", country="de")) == 1.0
    assert position_country_match(query, e("Position", country="fr")) == -1.0
    assert position_country_match(query, e("Position")) == 0.0
    assert position_country_match(e("Person", country="de"), query) == 0.0


def test_org_country_mismatch_only_flags_legal_entities():
    query = e("Company", country="de")

    assert org_country_mismatch(query, e("Company", country="de")) == 0.0
    assert org_country_mismatch(query, e("Company", country="fr")) == 1.0
    assert org_country_mismatch(query, e("Company")) == 0.0
    assert org_country_mismatch(e("Person", country="de"), e("Person", country="fr")) == 0.0


def test_person_country_mismatch_only_flags_people():
    query = e("Person", country="de")

    assert per_country_mismatch(query, e("Person", country="de")) == 0.0
    assert per_country_mismatch(query, e("Person", country="fr")) == 1.0
    assert per_country_mismatch(query, e("Person")) == 0.0
    assert per_country_mismatch(e("Company", country="de"), e("Company", country="fr")) == 0.0
