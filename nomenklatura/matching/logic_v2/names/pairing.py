from typing import List, Set

from rigour.names import NamePart, Symbol, Span

from nomenklatura.matching.logic_v2.names.magic import SYM_SCORES, SYM_WEIGHTS
from nomenklatura.matching.logic_v2.names.util import Match


class Pairing:
    __slots__ = [
        "query_used",
        "result_used",
        "matches",
        "_hash",
    ]

    def __init__(
        self,
        query_used: Set[NamePart],
        result_used: Set[NamePart],
        matches: List[Match],
    ) -> None:
        self.query_used = query_used
        self.result_used = result_used
        self.matches = matches

    @classmethod
    def empty(cls) -> "Pairing":
        """Create a new pairing with no matches."""
        return cls(
            query_used=set(),
            result_used=set(),
            matches=[],
        )

    def can_pair(self, query_span: Span, result_span: Span) -> bool:
        """Check if two spans can be paired."""
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

        if query_span.symbol.category in (Symbol.Category.NAME, Symbol.Category.NICK):
            # This may not be correct for many tokens since it's expected that the bulk
            # of filtered items will be single-part span.
            for qp, rp in zip(query_span.parts, result_span.parts):
                if not qp.can_match(rp):
                    return False

        return True

    def add(self, query_span: Span, result_span: Span) -> "Pairing":
        """Add a pair of spans to the pairing."""
        symbol = query_span.symbol
        # Some types of symbols effectively also work as soft stopwords, reducing the relevance
        # of the match. For example, "Ltd." in an organization name is not as informative as a
        # person's first name. That's why we're assigning a low weight, even for literal matches.
        match = Match(
            qps=query_span.parts,
            rps=result_span.parts,
            symbol=query_span.symbol,
            score=SYM_SCORES.get(symbol.category, 1.0),
            weight=SYM_WEIGHTS.get(symbol.category, 1.0),
        )
        return Pairing(
            self.query_used.union(query_span.parts),
            self.result_used.union(result_span.parts),
            self.matches + [match],
        )
