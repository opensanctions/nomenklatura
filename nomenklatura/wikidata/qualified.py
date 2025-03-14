from typing import Set
from followthemoney.helpers import dates_years

from nomenklatura.wikidata.model import Claim
from nomenklatura.wikidata.lang import LangText


def post_summary(
    position: LangText,
    start_dates: Set[str],
    end_dates: Set[str],
    dates: Set[str],
) -> LangText:
    """Make a string summary for a Post object."""
    start = min(dates_years(start_dates), default="")
    end = min(dates_years(end_dates), default="")
    date_range = None
    if len(start) or len(end):
        date_range = f"{start}-{end}"
    dates_ = dates_years(dates)
    if date_range is None and len(dates_):
        date_range = ", ".join(sorted(dates_))

    label = position.text
    if date_range:
        label = f"{label} ({date_range})"
    original = position.text or position.original
    return LangText(label, position.lang, original=original)


def qualify_value(value: LangText, claim: Claim) -> LangText:
    if value.text is None:
        return value
    starts: Set[str] = set()
    for qual in claim.get_qualifier("P580"):
        if qual.text.text is not None:
            starts.add(qual.text.text)

    ends: Set[str] = set()
    for qual in claim.get_qualifier("P582"):
        if qual.text.text is not None:
            ends.add(qual.text.text)

    dates: Set[str] = set()
    for qual in claim.get_qualifier("P585"):
        if qual.text.text is not None:
            dates.add(qual.text.text)

    return post_summary(value, starts, ends, dates)
