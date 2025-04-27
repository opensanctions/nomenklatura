import gzip
import logging
from functools import cache
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from rigour.text.dictionary import Scanner

from nomenklatura.matching.logic_v2.names.symbols import Symbol, SymbolName
from nomenklatura.matching.logic_v2.names.util import normalize_name
from nomenklatura.util import DATA_PATH

NAMES_PATH = DATA_PATH.joinpath("names.gz")
log = logging.getLogger(__name__)


class Tagger(Scanner):
    """A class to manage a dictionary of words and their aliases. This is used to perform replacement
    on those aliases or the word itself in a text.
    """

    def __init__(
        self,
        mapping: Dict[str, List[Symbol]],
    ) -> None:
        forms = list(mapping.keys())
        super().__init__(forms, ignore_case=False)
        self.mapping = mapping

    def __call__(self, text: Optional[str]) -> List[Tuple[str, Symbol]]:
        """Apply the tagger on a piece of pre-normalized text."""
        if text is None:
            return []
        symbols: List[Tuple[str, Symbol]] = []
        for match in self.pattern.finditer(text):
            value = match.group(1)
            for symbol in self.mapping.get(value, []):
                symbols.append((value, symbol))

        for token in text.split(" "):
            if token in self.mapping:
                for symbol in self.mapping[token]:
                    if (token, symbol) not in symbols:
                        symbols.append((token, symbol))
        return symbols


@cache
def get_org_tagger() -> Tagger:
    """Get the organization name tagger."""
    from rigour.data.names.data import ORG_SYMBOLS
    from rigour.data.names.org_types import ORG_TYPES

    log.info("Loading org type/symbol tagger...")

    mapping: Dict[str, List[Symbol]] = defaultdict(list)
    for key, values in ORG_SYMBOLS.items():
        sym = Symbol(Symbol.ORG_SYMBOL, key.upper())
        nkey = normalize_name(key)
        mapping[nkey].append(Symbol(Symbol.ORG_SYMBOL, key))
        for value in values:
            nvalue = normalize_name(value)
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    for org_type in ORG_TYPES:
        # TODO: should this apply to the display name or the compare name as separate symbols?
        type_key = org_type.get("compare", org_type.get("display"))
        if type_key is None:
            continue
        ot_sym = Symbol(Symbol.ORG_TYPE, type_key)
        display = org_type.get("display")
        if display is not None:
            mapping[normalize_name(display)].append(ot_sym)
        for alias in org_type.get("aliases", []):
            nalias = normalize_name(alias)
            if ot_sym not in mapping.get(nalias, []):
                mapping[nalias].append(ot_sym)

    return Tagger(mapping)


@cache
def get_person_tagger() -> Tagger:
    """Get the person name tagger."""
    from rigour.data.names.data import PERSON_SYMBOLS

    log.info("Loading person tagger...")

    mapping: Dict[str, List[Symbol]] = defaultdict(list)
    for key, values in PERSON_SYMBOLS.items():
        sym = Symbol(Symbol.PER_SYMBOL, key.upper())
        nkey = normalize_name(key)
        mapping[nkey].append(Symbol(Symbol.PER_SYMBOL, key))
        for value in values:
            nvalue = normalize_name(value)
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    with gzip.open(NAMES_PATH, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            names, qid = line.split(" => ")
            sym = Symbol(Symbol.PER_NAME, int(qid[1:]))
            names_norm: Set[str] = set()
            for alias in names.split(", "):
                names_norm.add(normalize_name(alias))
            if len(names_norm) > 1:
                for norm in names_norm:
                    mapping[norm].append(sym)

    log.info("Loaded person tagger (%s terms).", len(mapping))
    return Tagger(mapping)


def tag_org_name(name: SymbolName) -> None:
    """Tag the name with the organization type and symbol tags."""
    tagger = get_org_tagger()
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)


def tag_person_name(name: SymbolName) -> None:
    """Tag the name with the person name part and symbol tags."""
    tagger = get_person_tagger()
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)
