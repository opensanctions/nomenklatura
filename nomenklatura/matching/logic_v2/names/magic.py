from typing import List
from rigour.names import is_stopword
from rigour.names import Name, NamePart, Symbol


# Used when a match is two-sided (e.g. international~intl), to modify the importance of the match
# in the context of a set of matches.
SYM_WEIGHTS = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.INITIAL: 0.5,
    Symbol.Category.NICK: 0.8,
    # in "A B International" and "X International", we don't want to give too much weight to the symbol
    Symbol.Category.SYMBOL: 0.3,
    # Vessel 1 vs. Vessel 2 are very different.
    Symbol.Category.NUMERIC: 1.3,
    Symbol.Category.LOCATION: 0.8,
}

# Used when a match is one-sided (e.g. "international" in the query but not the result), to modify
# the impact of the extra name part on the score.
# For the categories not listed here, we give a weight of 1.0 (see weight_extra_match below)
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
    Symbol.Category.NUMERIC: 0.9,
    Symbol.Category.LOCATION: 0.9,
}


def weight_extra_match(parts: List[NamePart], name: Name) -> float:
    """Apply a weight to a name part which remained unmatched in the system, as a function
    of a user-supplied penalty, symbol weights, and some overrides."""
    if len(parts) == 1 and is_stopword(parts[0].form):
        return 0.5
    sparts = hash(tuple(parts))
    weight = 1.0
    categories = set()
    for span in name.spans:
        if span.symbol.category == Symbol.Category.NUMERIC:
            part = span.parts[0]
            if len(span.parts) == 1 and not part.numeric and len(part.comparable) < 2:
                continue
        if sparts == hash(tuple(span.parts)):
            categories.add(span.symbol.category)
            weight = weight * EXTRAS_WEIGHTS.get(span.symbol.category, 1.0)
    return weight
