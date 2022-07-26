from typing import TYPE_CHECKING
from followthemoney.helpers import post_summary

from nomenklatura.enrich.wikidata.model import Claim

if TYPE_CHECKING:
    from nomenklatura.enrich.wikidata import WikidataEnricher


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

    return post_summary(value, None, starts, ends, [])
