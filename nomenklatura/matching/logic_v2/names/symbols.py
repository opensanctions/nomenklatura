from enum import Enum
from typing import Any, List, Set
from rigour.names.name import Name
from rigour.names.tag import NameTypeTag
from rigour.names.part import NamePart


class Symbol:
    """A symbol is a semantic interpretation applied to one or more parts of a name."""

    class Category(Enum):
        ORG_TYPE = "org.type"
        ORG_SYMBOL = "org.symb"
        PER_ABBR = "per.abbr"
        PER_NAME = "per.name"
        PER_SYMBOL = "per.symb"
        PHONETIC = "phonetic"

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

    def __repr__(self) -> str:
        return f"<Symbol({self.category}, {self.id})>"


class Span:
    """A span is a part of a name that has been tagged with a symbol."""

    __slots__ = ["parts", "symbol"]

    def __init__(self, parts: List[NamePart], symbol: Symbol) -> None:
        self.parts = parts
        self.symbol = symbol


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

    def common_symbols(self, other: "SymbolName") -> Set[Symbol]:
        """Return the intersection of two SymbolName objects."""
        return self.symbols.intersection(other.symbols)

    def non_symbol_parts(self, symbols: Set[Symbol]) -> List[NamePart]:
        """Return a list of parts that are not explained by symbols."""
        ignore_parts: Set[NamePart] = set()
        for span in self.spans:
            if span.symbol in symbols:
                ignore_parts.update(span.parts)
        return [part for part in self.parts if part not in ignore_parts]
