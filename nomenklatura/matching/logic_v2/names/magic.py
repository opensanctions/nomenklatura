from typing import Dict
from rigour.names import NamePartTag, Symbol


SYM_WEIGHTS = {
    Symbol.Category.ORG_CLASS: 0.7,
    Symbol.Category.INITIAL: 0.5,
    Symbol.Category.NAME: 1.0,
    Symbol.Category.SYMBOL: 0.3,
    Symbol.Category.NUMERIC: 1.3,
    Symbol.Category.LOCATION: 0.8,
    # Symbol.Category.PHONETIC: 0.6,
}

SYM_SCORES = {
    Symbol.Category.ORG_CLASS: 0.8,
    Symbol.Category.INITIAL: 0.9,
    Symbol.Category.NAME: 0.9,
    Symbol.Category.SYMBOL: 0.9,
    Symbol.Category.NUMERIC: 0.9,
    Symbol.Category.LOCATION: 0.9,
}


PART_WEIGHTS: Dict[NamePartTag, float] = {
    NamePartTag.NUM: 3.0,
    NamePartTag.LEGAL: 0.9,
    NamePartTag.PATRONYMIC: 0.9,
    NamePartTag.MATRONYMIC: 0.9,
    NamePartTag.MIDDLE: 0.9,
}
