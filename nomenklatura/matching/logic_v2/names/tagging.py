import logging
from functools import cache
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from rigour.text.dictionary import Scanner
from rigour.names import load_person_names_mapping

from nomenklatura.matching.logic_v2.names.symbols import Symbol, SymbolName
from nomenklatura.matching.logic_v2.names.util import normalize_name

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


def common_symbols() -> Dict[str, List[Symbol]]:
    """Get the common symbols for names."""
    from rigour.data.names.data import ORDINALS

    mapping: Dict[str, List[Symbol]] = defaultdict(list)
    for key, values in ORDINALS.items():
        sym = Symbol(Symbol.Category.ORDINAL, key.upper())
        for value in values:
            nvalue = normalize_name(value)
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    return mapping


@cache
def get_org_tagger() -> Tagger:
    """Get the organization name tagger."""
    from rigour.data.names.data import ORG_SYMBOLS
    from rigour.data.names.org_types import ORG_TYPES

    log.info("Loading org type/symbol tagger...")

    mapping = common_symbols()
    for key, values in ORG_SYMBOLS.items():
        sym = Symbol(Symbol.Category.ORG_SYMBOL, key.upper())
        nkey = normalize_name(key)
        mapping[nkey].append(sym)
        for value in values:
            nvalue = normalize_name(value)
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    for org_type in ORG_TYPES:
        # TODO: should this apply to the display name or the compare name as separate symbols?
        class_sym: Optional[Symbol] = None
        type_sym: Optional[Symbol] = None
        compare = org_type.get("compare")
        if compare is not None:
            class_sym = Symbol(Symbol.Category.ORG_CLASS, compare)
        display = org_type.get("display")
        if display is not None:
            type_sym = Symbol(Symbol.Category.ORG_TYPE, display)
            mapping[normalize_name(display)].append(class_sym)
        for alias in org_type.get("aliases", []):
            nalias = normalize_name(alias)
            if type_sym is not None and type_sym not in mapping.get(nalias, []):
                mapping[nalias].append(type_sym)
            if class_sym is not None and class_sym not in mapping.get(nalias, []):
                mapping[nalias].append(class_sym)

    return Tagger(mapping)


def tag_org_name(name: SymbolName) -> None:
    """Tag the name with the organization type and symbol tags."""
    tagger = get_org_tagger()
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)


@cache
def get_person_tagger() -> Tagger:
    """Get the person name tagger."""
    from rigour.data.names.data import PERSON_SYMBOLS

    log.info("Loading person tagger...")

    mapping = common_symbols()
    for key, values in PERSON_SYMBOLS.items():
        sym = Symbol(Symbol.Category.PER_SYMBOL, key.upper())
        nkey = normalize_name(key)
        mapping[nkey].append(Symbol(Symbol.Category.PER_SYMBOL, key))
        for value in values:
            nvalue = normalize_name(value)
            if sym not in mapping.get(nvalue, []):
                mapping[nvalue].append(sym)

    name_mapping = load_person_names_mapping(normalizer=normalize_name)
    for name, qids in name_mapping.items():
        for qid in qids:
            sym = Symbol(Symbol.Category.PER_NAME, int(qid[1:]))
            mapping[name].append(sym)

    log.info("Loaded person tagger (%s terms).", len(mapping))
    return Tagger(mapping)


def tag_person_name(name: SymbolName) -> None:
    """Tag the name with the person name part and symbol tags."""
    tagger = get_person_tagger()
    for phrase, symbol in tagger(name.norm_form):
        name.apply_phrase(phrase, symbol)
