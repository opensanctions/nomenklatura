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

WD_PRECISION_DAY = 11
WD_PRECISION_MONTH = 10
WD_PRECISION_YEAR = 9
PRECISION = {
    WD_PRECISION_DAY: Precision.DAY,
    WD_PRECISION_MONTH: Precision.MONTH,
    WD_PRECISION_YEAR: Precision.YEAR,
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

        # > Wikidata years are always signed and padded to have between 4 and 16 digits.
        # cf. https://www.wikidata.org/wiki/Help:Dates#Precision
        sign = raw_time[0]
        time = raw_time.strip("+-")
        prec_id = cast(int, value.get("precision"))

        # Hacky, but set all old imprecise dates to the minimum date so persons
        # with historical birth dates are filtered out.

        if sign == "-":
            # Really old: Pharaoh Nebtawyre ruled around 1995 BC.
            # Comparisons without sign in return value would be broken, so use MIN_DATE sentinel.
            return LangText(MIN_DATE, original=raw_time)
        if time > "1900":
            if prec_id < WD_PRECISION_YEAR:
                # Current but too imprecise
                return LangText(None, original=raw_time)
        else:
            if prec_id < WD_PRECISION_YEAR:
                # Old and imprecise
                return LangText(MIN_DATE, original=raw_time)
        # We're left with a date with enough precision for upstream logic to make good decisions.

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
