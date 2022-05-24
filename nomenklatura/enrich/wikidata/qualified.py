from typing import TYPE_CHECKING, Iterable, Optional, Set

from nomenklatura.enrich.wikidata.model import Claim

if TYPE_CHECKING:
    from nomenklatura.enrich.wikidata import WikidataEnricher


def _position_date(dates: Iterable[Optional[str]]) -> Set[str]:
    cleaned: Set[str] = set()
    for date in dates:
        if date is not None:
            cleaned.add(date[:4])
    return cleaned


def make_position(
    main: str,
    comment: Optional[str],
    starts: Iterable[Optional[str]],
    ends: Iterable[Optional[str]],
    dates: Iterable[Optional[str]],
) -> str:
    position = main
    start = min(_position_date(starts), default="")
    end = min(_position_date(ends), default="")
    date_range = None
    if len(start) or len(end):
        date_range = f"{start}-{end}"
    dates_ = _position_date(dates)
    if date_range is None and len(dates_):
        date_range = ", ".join(sorted(dates_))

    bracketed = None
    if date_range and comment:
        bracketed = f"{comment}, {date_range}"
    else:
        bracketed = comment or date_range

    if bracketed:
        position = f"{position} ({bracketed})"
    return position


def qualify_value(enricher: "WikidataEnricher", value: str, claim: Claim) -> str:
    starts = set()
    for qual in claim.get_qualifier("P580"):
        starts.add(qual.text(enricher))

    ends = set()
    for qual in claim.get_qualifier("P582"):
        ends.add(qual.text(enricher))

    dates = set()
    for qual in claim.get_qualifier("P585"):
        dates.add(qual.text(enricher))

    return make_position(value, None, starts, ends, [])
