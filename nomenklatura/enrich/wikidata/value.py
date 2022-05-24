import logging
from prefixdate import Precision
from typing import TYPE_CHECKING, cast, Any, Dict, Optional

from nomenklatura.util import is_qid

if TYPE_CHECKING:
    from nomenklatura.enrich.wikidata import WikidataEnricher


log = logging.getLogger(__name__)
PRECISION = {
    11: Precision.DAY,
    10: Precision.MONTH,
    9: Precision.YEAR,
}


def snak_value_to_string(
    enricher: "WikidataEnricher", value_type: Optional[str], value: Dict[str, Any]
) -> Optional[str]:
    if value_type is None:
        return None
    elif value_type == "time":
        time = cast(Optional[str], value.get("time"))
        if time is not None:
            time = time.strip("+")
            prec_id = cast(int, value.get("precision"))
            prec = PRECISION.get(prec_id, Precision.DAY)
            time = time[: prec.value]
            # Date limit in FtM. These will be removed by the death filter:
            time = max("1001", time)
        return time
    elif value_type == "wikibase-entityid":
        return enricher.get_label(value.get("id"))
    elif value_type == "monolingualtext":
        return value.get("text")
    elif value_type == "quantity":
        # Resolve unit name and make into string:
        amount = cast(str, value.get("amount", ""))
        amount = amount.lstrip("+")
        unit = value.get("unit", "")
        unit = unit.split("/")[-1]
        if is_qid(unit):
            unit = enricher.get_label(unit)
            amount = f"{amount} {unit}"
        return amount
    elif isinstance(value, str):
        return value
    else:
        log.warning("Unhandled value [%s]: %s", value_type, value)
    return None
