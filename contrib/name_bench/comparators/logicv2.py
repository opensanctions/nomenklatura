"""Wrapper around nomenklatura's full LogicV2 matcher.

Used as the apples-to-apples reference for harness iterations. Run
once and freeze the per-case output as `run_data/logicv2-frozen.csv`
(see `--frozen` flag on `run.py`); future iterations diff against it
without re-running.
"""

from __future__ import annotations

from uuid import uuid4

from followthemoney import ValueEntity, model

from nomenklatura.matching.logic_v2.model import LogicV2

_CONFIG = LogicV2.default_config()


def logicv2_baseline(name1: str, name2: str, schema: str) -> float:
    """Run LogicV2.compare on a synthesised single-property entity pair.

    cases.csv only carries `name` strings (not full FtM entities), so we
    construct minimal Entity instances with just the `name` property
    populated. Identifiers, country, DOB etc. are absent — LogicV2's
    name-distance pathway carries the whole verdict.
    """
    schema_obj = model.get(schema)
    if schema_obj is None:
        return 0.0
    qry = ValueEntity(schema_obj, {"id": uuid4().hex})
    qry.add("name", name1)
    cdt = ValueEntity(schema_obj, {"id": uuid4().hex})
    cdt.add("name", name2)
    return float(LogicV2.compare(qry, cdt, _CONFIG).score)
