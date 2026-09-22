from collections.abc import Sequence

from rigour.names import Name, NamePart, NamePartTag, Symbol

# Used when a match is two-sided (e.g. international~intl), to modify the importance of the match
# in the context of a set of matches.
SYM_WEIGHTS = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.INITIAL: 0.5,
    Symbol.Category.NICK: 0.8,
    # in "A B International" and "X International", we don't want to give too much weight to the symbol
    Symbol.Category.SYMBOL: 0.3,
    # in "A B Medical" and "A B Casino", the symbol is a stronger signal than "International" or "Company"
    Symbol.Category.DOMAIN: 0.7,
    # Vessel 1 vs. Vessel 2 are very different.
    Symbol.Category.NUMERIC: 1.3,
    Symbol.Category.LOCATION: 0.8,
}

# Used when a match is one-sided (e.g. "international" in the query but not the result), to modify
# the impact of the extra name part on the score.
# Categories not listed here leave the weight unchanged.
EXTRAS_WEIGHTS = {
    # Siemens AG vs. Siemens, sometimes the org class is omitted
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.SYMBOL: 0.7,
    # PE Fund 1 vs. PE Fund, often investments funds are numbered and that's quite important
    Symbol.Category.NUMERIC: 1.3,
    # Siemens Russia vs. Siemens: we don't care that much because in a local context,
    # it's common to omit the suffix of the local subsidiary.
    Symbol.Category.LOCATION: 0.8,
}

SYM_SCORES = {
    Symbol.Category.ORG_CLASS: 0.8,
    Symbol.Category.INITIAL: 0.9,
    Symbol.Category.NAME: 0.9,
    Symbol.Category.NICK: 0.6,
    Symbol.Category.SYMBOL: 0.9,
    Symbol.Category.DOMAIN: 0.9,
    Symbol.Category.NUMERIC: 0.9,
    Symbol.Category.LOCATION: 0.9,
}


def extra_match_weights(name: Name) -> dict[tuple[NamePart, ...], float]:
    """Fold the extras weights of a name's spans into a lookup keyed by span parts.

    Build this once per name and hand it to `weight_extra_match`, which is called
    once per unmatched part per symbol pairing. Spans whose category leaves the
    weight at 1.0 are omitted, so most person names yield an empty table.
    """
    weights: dict[tuple[NamePart, ...], float] = {}
    for span in name.spans:
        category = span.symbol.category
        if category == Symbol.Category.NUMERIC:
            part = span.parts[0]
            if len(span.parts) == 1 and not part.numeric and len(part.comparable) < 2:
                continue
        weight = EXTRAS_WEIGHTS.get(category, 1.0)
        if weight == 1.0:
            continue
        weights[span.parts] = weights.get(span.parts, 1.0) * weight
    return weights


def weight_extra_match(
    parts: Sequence[NamePart], weights: dict[tuple[NamePart, ...], float]
) -> float:
    """Weight a name part which remained unmatched, using the table built by
    `extra_match_weights` for the name the part belongs to."""
    if len(parts) == 1 and parts[0].tag == NamePartTag.STOP:
        return 0.5
    return weights.get(tuple(parts), 1.0)
