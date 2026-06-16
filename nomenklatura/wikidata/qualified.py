from typing import Set
from followthemoney.helpers import post_summary

from nomenklatura.wikidata.model import Claim
from nomenklatura.wikidata.lang import LangText


def qualify_value(value: LangText, claim: Claim) -> LangText:
    if value.text is None:
        return value
    if claim.deprecated:
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

    label = post_summary(value.text, None, starts, ends, dates)
    original = value.text or value.original
    return LangText(label, value.lang, original=original)
