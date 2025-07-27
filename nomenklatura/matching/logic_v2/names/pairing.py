from typing import Dict, List, Set

from rigour.names import NamePart, Symbol, Name, Span


class Pairing:
    __slots__ = [
        "query",
        "query_used",
        "result",
        "result_used",
        "symbols",
        "_hash",
    ]

    def __init__(
        self,
        query: Name,
        result: Name,
        query_used: Set[NamePart],
        result_used: Set[NamePart],
        symbols: Dict[Symbol, bool],
    ) -> None:
        self.query = query
        self.query_used = query_used
        self.result = result
        self.result_used = result_used
        self.symbols = symbols

    @classmethod
    def create(cls, query: Name, result: Name) -> "Pairing":
        """Create a new pairing."""
        return cls(
            query=query,
            result=result,
            query_used=set(),
            result_used=set(),
            symbols={},
        )

    def can_pair(self, query_span: Span, result_span: Span) -> bool:
        """Check if two spans can be paired."""
        # if query_span.symbol.category != result_span.symbol.category:
        #     return False
        if self.query_used.intersection(query_span.parts):
            return False
        if self.result_used.intersection(result_span.parts):
            return False

        # If the text is actually identical, we do not need to establish
        # a pairing, as it is already a match.
        # revised: This doesn't work because it knocks out the stopword-like functionality of
        # symbolic matching.
        # if query_span.form == result_span.form:
        #     return False

        # Check if one at least of the two span parts is a name initial
        if query_span.symbol.category == Symbol.Category.INITIAL:
            if len(query_span.parts[0]) > 1 and len(result_span.parts[0]) > 1:
                return False

        if query_span.symbol.category == Symbol.Category.NAME:
            # This may not be correct for many tokens since it's expected that the bulk
            # of filtered items will be single-part span.
            for qp, rp in zip(query_span.parts, result_span.parts):
                if not qp.can_match(rp):
                    return False

        return True

    def add(self, query_span: Span, result_span: Span) -> "Pairing":
        """Add a pair of spans to the pairing."""
        symbols = self.symbols.copy()
        symbols[query_span.symbol] = query_span.comparable == result_span.comparable
        return Pairing(
            self.query,
            self.result,
            self.query_used.union(query_span.parts),
            self.result_used.union(result_span.parts),
            symbols,
        )

    def query_remainder(self) -> List[NamePart]:
        """Get the remaining query parts."""
        return [part for part in self.query.parts if part not in self.query_used]

    def result_remainder(self) -> List[NamePart]:
        """Get the remaining result parts."""
        return [part for part in self.result.parts if part not in self.result_used]

    def __repr__(self) -> str:
        """String representation of the pairing."""
        qrem = ":".join([p.form for p in self.query_remainder()])
        rrem = ":".join([p.form for p in self.result_remainder()])
        return f"Pairing(qrem={qrem}, rrem={rrem}, symbols={self.symbols})"
