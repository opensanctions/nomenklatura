"""Emulation of OFAC's Sanctions List Search scoring.

Reverse-engineered from the public tool at
`sanctionssearch.ofac.treas.gov` plus FAQ 249. Tracks OFAC's reported
score within +/-5 points on 95.7% of a 164-row parity fixture; mean
absolute error 1.5 points.

This is not a "good" name matcher in the academic sense - it
inherits OFAC's quirks (single-token explosions, token-order
asymmetry, the per-token-pair scoring cliff at JW 0.5). For a
recall-vs-precision calibrated screener, see
`logic_v2`. This module exists so customers
can self-serve "what would OFAC say about this name?" without
round-tripping to treasury.gov.

Three mechanisms each match an observed quirk:

1. **Whole-string JW gated by first-letter** (`_whole_string_score`).
   The `BUSH GEORGE` query returns 0 hits while `GEORGE BUSH` returns
   3 - same tokens, reversed order. So OFAC's whole-string match is
   gated on the literal `input[0] == candidate[0]`.

2. **Jaro-Winkler without the 0.7 boost threshold**
   (`_simmetrics_jw`). OFAC's front end is ASP.NET WebForms with
   AjaxControlToolkit (vintage 2008-2012 .NET 3.5/4.0 stack), so
   SimMetrics-Java-style JW - prefix bonus applied unconditionally
   rather than gated on `pure Jaro >= 0.7` - is the most likely
   variant their contractor reached for. See `_simmetrics_jw` for
   the algorithmic detail and the long-candidate evidence.

3. **Per-token best-pairing JW with a 0.5 floor**
   (`_per_token_score`), plus dropping <=2-char query tokens
   (`_drop_short_tokens`). The short-token rule resolves the
   KIM JONG UN case where OFAC matches 5 different individuals at
   100 - `UN` gets dropped, leaving `KIM JONG` as the comparison.
   See `_per_token_score` for the floor mechanism.

The score is the max of the two techniques (FAQ 249).

The entity-level wrapper `ofac_name_score` lifts this string->string
score to the followthemoney level by taking the max over every
(query_name, candidate_name) pair. This approximates OFAC's
alias-aware scoring: OFAC scores against the best of an entity's
aliases.
"""

from typing import List, Optional
from rigour.names import tokenize_name
from rigour._core import raw_jaro, raw_jaro_winkler
from followthemoney.proxy import E
from followthemoney.types import registry

from nomenklatura.matching.types import FtResult, ScoringConfig
from nomenklatura.matching.util import FNUL, type_pair


# Tuned against the 164-row positive fixture. Each constant resolves
# at least one observable OFAC quirk.
PER_PAIR_JW_FLOOR = 0.5     # per-token-pair JW below this contributes 0
SHORT_TOKEN_MAX_LEN = 2     # input tokens this short get dropped (with safety)
WINKLER_PREFIX_MAX = 4      # standard Winkler prefix cap (1990 paper)
WINKLER_WEIGHT = 0.1        # standard Winkler scaling factor (1990 paper)


def _simmetrics_jw(left: str, right: str) -> float:
    """SimMetrics-style Jaro-Winkler: prefix bonus applied
    unconditionally (no 0.7 boost threshold). The 1990 Winkler
    paper gates the bonus on `pure Jaro >= 0.7`; modern libraries
    honour that, the classic SimMetrics-Java library does not.
    The threshold-honouring variant under-scores long candidates
    with shared prefixes - e.g.
    `VLADIMIR PUTIN <-> VLADIMIROVKA ADVANCED WEAPONS AND RESEARCH
    COMPLEX` lands at 82 in OFAC but just 64 with standard JW. We
    compute pure Jaro via `raw_jaro` and apply the prefix bonus
    ourselves to recover that cluster."""
    if not left or not right:
        return 0.0
    jaro = raw_jaro(left, right)
    if jaro == 0.0:
        return 0.0
    prefix_matches = 0
    for left_char, right_char in zip(
        left[:WINKLER_PREFIX_MAX], right[:WINKLER_PREFIX_MAX]
    ):
        if left_char == right_char:
            prefix_matches += 1
        else:
            break
    return jaro + prefix_matches * WINKLER_WEIGHT * (1 - jaro)


def _tokens(name: str) -> List[str]:
    """Tokenise via rigour's Unicode-aware splitter, then uppercase.
    Apostrophes / commas / periods are deleted (combining-mark
    category), not split on - `O'BRIEN` stays one token."""
    return [token.upper() for token in tokenize_name(name)]


def _drop_short_tokens(tokens: List[str]) -> List[str]:
    """Strip tokens of length <= SHORT_TOKEN_MAX_LEN, but never empty
    the list - a single-char query like `Z` keeps its lone token."""
    kept = [t for t in tokens if len(t) > SHORT_TOKEN_MAX_LEN]
    return kept or tokens


def _whole_string_score(query: str, candidate: str) -> float:
    """Whole-string SimMetrics-JW, gated by `input[0] == candidate[0]`.
    FAQ 249's whole-string technique."""
    query_norm = " ".join(_tokens(query))
    candidate_norm = " ".join(_tokens(candidate))
    if not query_norm or not candidate_norm or query_norm[0] != candidate_norm[0]:
        return 0.0
    return _simmetrics_jw(query_norm, candidate_norm)


def _per_token_score(query: str, candidate: str) -> float:
    """Per-token best-pairing JW score, FAQ 249's per-name-part technique.

    Tokenise both names; drop short query tokens (see
    `_drop_short_tokens`). For each remaining query token, find its
    best Jaro-Winkler match against any candidate token; zero pairs
    scoring below `PER_PAIR_JW_FLOOR`. Return the mean across kept
    query tokens.

    The floor acts as a soft first-letter check: tokens with
    mismatched leading characters land below it naturally, without
    an explicit gate. Example: `GEORGE BUSH <-> HASWANI, George`
    scores 50 in OFAC because `BUSH<->HASWANI` is 0.46 (zeroed); a
    plain mean would give 73.

    Per-token JW rarely sits in the 0.6-0.7 band where the 1990
    threshold matters, so `raw_jaro_winkler` is fine here."""
    query_tokens = _drop_short_tokens(_tokens(query))
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    pair_scores = []
    for query_token in query_tokens:
        best = max(
            (
                raw_jaro_winkler(query_token, candidate_token)
                for candidate_token in candidate_tokens
            ),
            default=0.0,
        )
        pair_scores.append(best if best >= PER_PAIR_JW_FLOOR else 0.0)
    return sum(pair_scores) / len(pair_scores)


def ofac_score(query: str, candidate: str) -> int:
    """Approximate OFAC's Sanctions List Search score for a `query`
    name against a `candidate` name on the SDN list. Returns an
    integer 0-100 mirroring OFAC's slider scale.

    Tracks OFAC's reported score within +/-5 points on 95.7% of a
    164-row parity fixture; mean absolute error 1.5 points."""
    whole = _whole_string_score(query, candidate)
    per_token = _per_token_score(query, candidate)
    return round(max(whole, per_token) * 100)


def ofac_name_score(query: E, result: E, config: ScoringConfig) -> FtResult:
    """Compare two entities by taking the maximum OFAC-style score
    over every (query name, candidate name) pair. Mirrors OFAC's
    alias-aware scoring, where the reported score is against the
    best of an entity's aliases."""
    query_names, result_names = type_pair(query, result, registry.name)
    if not query_names or not result_names:
        return FtResult(score=FNUL, detail=None)
    best: float = FNUL
    best_query: Optional[str] = None
    best_candidate: Optional[str] = None
    for query_name in query_names:
        for candidate_name in result_names:
            score = ofac_score(query_name, candidate_name) / 100.0
            if score > best:
                best = score
                best_query = query_name
                best_candidate = candidate_name
    if best_query is None:
        return FtResult(score=FNUL, detail=None)
    return FtResult(
        score=best, detail=None, query=best_query, candidate=best_candidate
    )
