from typing import TYPE_CHECKING, Set
from followthemoney.helpers import dates_years

from nomenklatura.enrich.wikidata.model import Claim
from nomenklatura.enrich.wikidata.lang import LangText

if TYPE_CHECKING:
    from nomenklatura.enrich.wikidata import WikidataEnricher


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


def qualify_value(
    enricher: "WikidataEnricher", value: LangText, claim: Claim
) -> LangText:
    if value.text is None:
        return value
    starts: Set[str] = set()
    for qual in claim.get_qualifier("P580"):
        label = qual.text(enricher)
        if label.text is not None:
            starts.add(label.text)

    ends: Set[str] = set()
    for qual in claim.get_qualifier("P582"):
        label = qual.text(enricher)
        if label.text is not None:
            ends.add(label.text)

    dates: Set[str] = set()
    for qual in claim.get_qualifier("P585"):
        label = qual.text(enricher)
        if label.text is not None:
            dates.add(label.text)

    return post_summary(value, starts, ends, dates)
