from nomenklatura.matching.name_based.misc import orgid_disjoint
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

config = ScoringConfig.defaults()


def test_orgid_disjoint():
    query = e("Company", registrationNumber="77401103")
    result = e("Company", registrationNumber="77401103")
    assert orgid_disjoint(query, result, config).score == 0.0
    result = e("Company", idNumber="77401103")
    assert orgid_disjoint(query, result, config).score == 0.0
    result = e("Company", name="BLA CORP")
    assert orgid_disjoint(query, result, config).score == 0.0
    result = e("Company", registrationNumber="E77401103")
    assert orgid_disjoint(query, result, config).score > 0.0
    assert orgid_disjoint(query, result, config).score < 1.0
    result = e("Company", registrationNumber="83743878")
    assert orgid_disjoint(query, result, config).score == 1.0
