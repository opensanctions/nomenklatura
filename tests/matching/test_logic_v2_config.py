from nomenklatura.matching.logic_v2.model import LogicV2
from .util import e

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
