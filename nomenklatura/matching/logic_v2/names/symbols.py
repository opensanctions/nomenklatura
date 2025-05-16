from enum import Enum
from typing import Any, Dict, List, Set
from rigour.names.name import Name
from rigour.names.tag import NameTypeTag
from rigour.names.part import NamePart

from nomenklatura.util import list_intersection


class Symbol:
    """A symbol is a semantic interpretation applied to one or more parts of a name."""

    class Category(Enum):
        ORG_TYPE = "org.type"
        ORG_CLASS = "org.class"
        ORG_SYMBOL = "org.symbol"
        PER_INIT = "per.initial"
        PER_NAME = "per.name"
        PER_SYMBOL = "per.symbol"
        ORDINAL = "ordinal"
        PHONETIC = "phonetic"

    __slots__ = ["category", "id"]

    def __init__(self, category: Category, id: Any) -> None:
        """Create a symbol with a category and an id."""
        # TODO: can it be used multiple times?
        # TODO: does it involve a discount?
        self.category = category
        self.id = id

    def __hash__(self) -> int:
        return hash((self.category, self.id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.category == other.category and self.id == other.id

    def __repr__(self) -> str:
        return f"<Symbol({self.category}, {self.id})>"


class Span:
    """A span is a part of a name that has been tagged with a symbol."""

    __slots__ = ["parts", "symbol"]

    def __init__(self, parts: List[NamePart], symbol: Symbol) -> None:
        self.parts = parts
        self.symbol = symbol

    def __hash__(self) -> int:
        return hash((tuple(self.parts), self.symbol))

    def __eq__(self, other: Any) -> bool:
        try:
            return bool(self.symbol == other.symbol and self.parts == other.parts)
        except AttributeError:
            return False


class SymbolName(Name):
    def __init__(self, original: str, form: str, tag: NameTypeTag) -> None:
        super().__init__(original, form=form, tag=tag)
        self.spans: List[Span] = []

    def apply_phrase(self, phrase: str, symbol: Symbol) -> None:
        """Apply a symbol to a phrase in the name."""
        matching: List[NamePart] = []
        tokens = phrase.split(" ")
        for part in self.parts:
            next_token = tokens[len(matching)]
            if part.form == next_token:
                matching.append(part)
            if len(matching) == len(tokens):
                self.spans.append(Span(matching, symbol))
                matching = []

    def apply_part(self, part: NamePart, symbol: Symbol) -> None:
        """Apply a symbol to a part of the name."""
        self.spans.append(Span([part], symbol))

    @property
    def symbols(self) -> Set[Symbol]:
        """Return a dictionary of symbols applied to the name."""
        symbols: Set[Symbol] = set()
        for span in self.spans:
            symbols.add(span.symbol)
        return symbols

    @property
    def norm_form(self) -> str:
        """Return the normalized form of the name."""
        return " ".join([part.form for part in self.parts])

    def contains(self, other: "SymbolName") -> bool:
        """Check if this name contains another name."""
        if self == other or self.tag == NameTypeTag.UNK:
            return False
        if len(self.parts) < len(other.parts):
            return False
        if self.tag == NameTypeTag.PER:
            forms = [part.form for part in self.parts]
            other_forms = [part.form for part in other.parts]
            return list_intersection(forms, other_forms) == len(other_forms)
        return other.norm_form in self.norm_form

    def symbol_map(self) -> Dict[Symbol, List[Span]]:
        """Return a mapping of symbols to their string representations."""
        symbol_map: Dict[Symbol, List[Span]] = {}
        for span in self.spans:
            if span.symbol not in symbol_map:
                symbol_map[span.symbol] = []
            symbol_map[span.symbol].append(span)
        return symbol_map
