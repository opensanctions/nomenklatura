from nomenklatura.matching.logic_v2.model import LogicV2

from ..factory import e

CONFIG = LogicV2.default_config()


def test_disable_feature():
    p1 = e("Person", name="Vladimir Putin", weakAlias="Schnitzel")
    p2 = e("Person", name="Barack Obama", weakAlias="Schnitzel")

    config = LogicV2.default_config()
    matches = LogicV2.compare(p1, p2, config)
    assert matches.score > 0.7

    config = LogicV2.default_config()
    config.weights["weak_alias_match"] = 0.0
    matches = LogicV2.compare(p1, p2, config)
    assert matches.score == 0.0


def test_address_match_weight():
    c1 = e("Company", name="Acme Inc", address="123 Main St, Springfield, IL")
    c2 = e("Company", name="Wayne Corp", address="Main St 123, Springfield, IL")

    # Disabled by default, so an address alone does not produce a match:
    config = LogicV2.default_config()
    assert LogicV2.compare(c1, c2, config).score == 0.0

    config = LogicV2.default_config()
    config.weights["address_match"] = 0.6
    result = LogicV2.compare(c1, c2, config)
    # The address_prop_match bonus is not added on top of address_match:
    assert result.score == 0.6
    assert result.explanations["address_match"].score == 1.0

    # As supporting evidence for a name match, the address bonus still applies:
    c3 = e("Company", name="Acme Inc", address="Main St 123, Springfield, IL")
    result = LogicV2.compare(c1, c3, config)
    assert result.score == 1.0
