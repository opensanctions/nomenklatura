from enum import Enum
from typing import Any, Dict, List, Set
from rigour.names.name import Name
from rigour.names.tag import NameTypeTag
from rigour.names.part import NamePart

from nomenklatura.util import list_intersection


class Symbol:
    """A symbol is a semantic interpretation applied to one or more parts of a name."""

    class Category(Enum):
        ORG_CLASS = "ORGCLASS"
        SYMBOL = "SYMBOL"
        INITIAL = "INITIAL"
        NAME = "NAME"
        ORDINAL = "ORD"
        PHONETIC = "PHON"

    __slots__ = ["category", "id"]

    def __init__(self, category: Category, id: Any) -> None:
        """Create a symbol with a category and an id."""
        self.category = category
        self.id = id

    def __hash__(self) -> int:
        return hash((self.category, self.id))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Symbol):
            return False
        return self.category == other.category and self.id == other.id

    def __str__(self) -> str:
        return f"[{self.category.value}:{self.id}]"

    def __repr__(self) -> str:
        return f"<Symbol({self.category}, {self.id})>"


class Span:
    """A span is a set of parts of a name that have been tagged with a symbol."""

    __slots__ = ["parts", "symbol"]

    def __init__(self, parts: List[NamePart], symbol: Symbol) -> None:
        self.parts = tuple(parts)
        self.symbol = symbol

    @property
    def maybe_ascii(self) -> str:
        """Return the string representation of the span."""
        return " ".join([part.maybe_ascii for part in self.parts])

    def __hash__(self) -> int:
        return hash((self.parts, self.symbol))

    def __eq__(self, other: Any) -> bool:
        try:
            return bool(self.symbol == other.symbol and self.parts == other.parts)
        except AttributeError:
            return False

    def __repr__(self) -> str:
        return f"<Span({self.parts!r}, {self.symbol})>"


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
            common_forms = list_intersection(forms, other_forms)

            # we want to make this support middle initials so that
            # "John Smith" can match "J. Smith"
            for ospan in other.spans:
                if ospan.symbol.category == Symbol.Category.INITIAL:
                    if len(ospan.parts[0].form) > 1:
                        continue
                    for span in self.spans:
                        if span.symbol == ospan.symbol:
                            common_forms.append(ospan.maybe_ascii)

            # If every part of the other name is represented in the common forms,
            # we consider it a match.
            if len(common_forms) == len(other_forms):
                return True

        return other.norm_form in self.norm_form

    def symbol_map(self) -> Dict[Symbol, List[Span]]:
        """Return a mapping of symbols to their string representations."""
        symbol_map: Dict[Symbol, List[Span]] = {}
        for span in self.spans:
            if span.symbol not in symbol_map:
                symbol_map[span.symbol] = []
            symbol_map[span.symbol].append(span)
        return symbol_map
