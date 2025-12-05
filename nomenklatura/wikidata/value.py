import logging
from prefixdate import Precision
from typing import TYPE_CHECKING, Set, cast, Any, Dict, Optional
from rigour.ids.wikidata import is_qid
from rigour.text.cleaning import remove_emoji, remove_bracketed_text
from rigour.names import is_name
# from rigour.text.distance import is_levenshtein_plausible

from nomenklatura.wikidata.lang import LangText

if TYPE_CHECKING:
    from nomenklatura.wikidata.client import WikidataClient


log = logging.getLogger(__name__)
MIN_DATE = "1001"
PRECISION = {
    11: Precision.DAY,
    10: Precision.MONTH,
    9: Precision.YEAR,
}


def snak_value_to_string(
    client: "WikidataClient", value_type: Optional[str], value: Dict[str, Any]
) -> LangText:
    if value_type is None:
        return LangText(None)
    elif value_type == "time":
        raw_time = cast(Optional[str], value.get("time"))
        if raw_time is None:
            return LangText(None)
        if raw_time.startswith("-"):
            return LangText(None, original=raw_time)  # No BC dates
        time = raw_time.strip("+")
        prec_id = cast(int, value.get("precision"))

        # cf. https://www.wikidata.org/wiki/Help:Dates#Precision
        # Even old dates have 
        # Atilla the Hun:
        #   "time": "+0395-00-00T00:00:00Z",
        #   "precision": 9
        # His daughter born 5th century, precision 7, time="+0500-01-01..."
        # So century precision still has millennium zero padding.

        # Precision less than millennium
        if prec_id < 6:
            return LangText(None, original=raw_time) 
        #  before 1900
        if time < "1900":
            # Hacky, but set all old dates to the minimum date so persons
            # with historical birth dates are filtered out.
            return LangText(MIN_DATE, original=raw_time)
        prec = PRECISION.get(prec_id, Precision.DAY)
        time = time[: prec.value]

        # Remove Jan 01, because it seems to be in input failure pattern
        # with Wikidata (probably from bots that don't get "precision").
        if time.endswith("-01-01"):
            time = time[:4]

        # Date limit in FtM. These will be removed by the death filter:
        time = max(MIN_DATE, time)
        return LangText(time, original=raw_time)
    elif value_type == "wikibase-entityid":
        qid = value.get("id")
        return client.get_label(qid)
    elif value_type == "monolingualtext":
        text = value.get("text")
        if isinstance(text, str):
            return LangText(text, lang=value.get("language"))
    elif value_type == "quantity":
        # Resolve unit name and make into string:
        raw_amount = cast(str, value.get("amount", ""))
        amount = raw_amount.lstrip("+")
        unit = value.get("unit", "")
        unit = unit.split("/")[-1]
        if is_qid(unit):
            unit = client.get_label(unit)
            amount = f"{amount} {unit}"
        return LangText(amount, original=raw_amount)
    elif isinstance(value, str):
        return LangText(value)
    else:
        log.warning("Unhandled value [%s]: %s", value_type, value)
    return LangText(None)


def clean_name(name: str) -> Optional[str]:
    """Clean a name for storage, try to throw out dangerous user inputs."""
    if not is_name(name):
        return None
    clean_name = remove_bracketed_text(name)
    if not is_name(clean_name):
        clean_name = name
    return remove_emoji(clean_name)


def is_alias_strong(alias: str, names: Set[str]) -> bool:
    """Check if an alias is a plausible nickname for a person, ie. shows some
    similarity to the actual name."""
    if " " not in alias:
        return False
    # for name in names:
    #     if is_levenshtein_plausible(alias, name, max_edits=None, max_percent=0.7):
    #         return True
    return True
