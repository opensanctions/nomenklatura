from typing import List
from rigour.names import is_stopword
from rigour.names import Name, NamePart, Symbol


SYM_WEIGHTS = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.INITIAL: 0.5,
    Symbol.Category.NICK: 0.8,
    Symbol.Category.SYMBOL: 0.3,
    Symbol.Category.NUMERIC: 1.3,
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

SYM_EXTRA_WEIGHT_OVERRIDES = {
    Symbol.Category.SYMBOL: 0.7,
}


def weight_extra_match(parts: List[NamePart], name: Name, base: float) -> float:
    """Apply a weight to a name part which remained unmatched in the system, as a function
    of a user-supplied penalty, symbol weights, and some overrides."""
    if len(parts) == 1 and is_stopword(parts[0].form):
        return base * 0.5
    sparts = hash(tuple(parts))
    weight = 1.0
    categories = set()
    for span in name.spans:
        if span.symbol.category in (Symbol.Category.INITIAL, Symbol.Category.NICK):
            continue
        if sparts == hash(tuple(span.parts)):
            categories.add(span.symbol.category)
            sym_weight = SYM_WEIGHTS.get(span.symbol.category, 1.0)
            weight = weight * SYM_EXTRA_WEIGHT_OVERRIDES.get(
                span.symbol.category, sym_weight
            )
    # print(categories, base, weight, base * weight)
    return base * weight
