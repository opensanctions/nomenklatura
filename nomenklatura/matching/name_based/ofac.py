"""Emulation of OFAC's Sanctions List Search scoring.

Reverse-engineered from the public tool at
`sanctionssearch.ofac.treas.gov` plus FAQ 249. Tracks OFAC's reported
score within +/-5 points on 95.7% of a 164-row parity fixture; mean
absolute error 1.5 points.

This is not a "good" name matcher in the academic sense - it
inherits OFAC's quirks (single-token explosions, length-asymmetric
behavior, the per-pair JW < 0.5 cliff). For a recall-vs-precision
calibrated screener, see `nomenklatura.matching.logic_v2`. This
module exists so customers can self-serve "what would OFAC say
about this name?" without round-tripping to treasury.gov.

Three mechanisms each match an observed quirk:

1. **Whole-string JW gated by first-letter** (`_whole_string_score`).
   The `BUSH GEORGE` query returns 0 hits while `GEORGE BUSH` returns
   3 - same tokens, reversed order. So OFAC's whole-string match is
   gated on the literal `input[0] == candidate[0]`.

2. **Jaro-Winkler without the 0.7 boost threshold**
   (`_simmetrics_jw`). The 1990 Winkler paper recommends only applying
   the prefix bonus when pure Jaro >= 0.7. Modern libs (rigour,
   rapidfuzz, jellyfish) honour that threshold. The classic
   SimMetrics-Java library does not - it applies the bonus
   unconditionally. OFAC's front end is ASP.NET WebForms with
   AjaxControlToolkit (vintage 2008-2012 .NET 3.5/4.0 stack), so
   SimMetrics-style is the most likely JW their contractor reached
   for. This single change recovers the long-candidate cluster
   (`VLADIMIR PUTIN <-> VLADIMIROVKA ADVANCED WEAPONS AND RESEARCH
   COMPLEX` 82 vs standard JW 64). We get pure Jaro from
   `rigour._core.raw_jaro` and apply the prefix bonus ourselves.

3. **Per-input-token best-pairing JW with a 0.5 floor**
   (`_per_token_score`). `GEORGE BUSH <-> HASWANI, George` scores 50
   in OFAC (a perfect GEORGE-George match averaged with a near-zero
   BUSH-HASWANI). A simple mean would give 73; zeroing the
   BUSH-HASWANI pair (JW = 0.46 < 0.5) gives 50 exactly. Combined
   with dropping <=2-char input tokens (with single-token safety),
   this also resolves the KIM JONG UN case where OFAC matches 5
   different individuals at 100.

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


def _simmetrics_jw(a: str, b: str) -> float:
    """SimMetrics-style Jaro-Winkler: prefix bonus applied
    unconditionally (no 0.7 boost threshold). See module docstring
    for why this matches OFAC where standard threshold-honoring JW
    does not."""
    if not a or not b:
        return 0.0
    j = raw_jaro(a, b)
    if j == 0.0:
        return 0.0
    prefix_matches = 0
    for ca, cb in zip(a[:WINKLER_PREFIX_MAX], b[:WINKLER_PREFIX_MAX]):
        if ca == cb:
            prefix_matches += 1
        else:
            break
    return j + prefix_matches * WINKLER_WEIGHT * (1 - j)


def _tokens(s: str) -> List[str]:
    """Tokenise via rigour's Unicode-aware splitter, then uppercase.
    Apostrophes / commas / periods are deleted (combining-mark
    category), not split on - `O'BRIEN` stays one token."""
    return [t.upper() for t in tokenize_name(s)]


def _drop_short_tokens(toks: List[str]) -> List[str]:
    """Strip tokens of length <= SHORT_TOKEN_MAX_LEN, but never empty
    the list - a single-char query like `Z` keeps its lone token."""
    kept = [t for t in toks if len(t) > SHORT_TOKEN_MAX_LEN]
    return kept or toks


def _whole_string_score(query: str, candidate: str) -> float:
    """Whole-string SimMetrics-JW, gated by `input[0] == candidate[0]`.
    FAQ 249 Technique 1."""
    q = " ".join(_tokens(query))
    c = " ".join(_tokens(candidate))
    if not q or not c or q[0] != c[0]:
        return 0.0
    return _simmetrics_jw(q, c)


def _per_token_score(query: str, candidate: str) -> float:
    """Per-input-token best-pairing JW, mean over input tokens. Pairs
    with JW < `PER_PAIR_JW_FLOOR` contribute 0 to the mean - the soft
    first-letter check that's implicit in JW magnitude. Per-token
    comparisons rarely fall below the 0.7 Jaro floor, so the standard
    threshold-honoring JW is fine here. FAQ 249 Technique 2."""
    query_tokens = _drop_short_tokens(_tokens(query))
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    pair_scores = []
    for qt in query_tokens:
        best = max(
            (raw_jaro_winkler(qt, ct) for ct in candidate_tokens),
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
    best_q: Optional[str] = None
    best_c: Optional[str] = None
    for q in query_names:
        for c in result_names:
            score = ofac_score(q, c) / 100.0
            if score > best:
                best = score
                best_q = q
                best_c = c
    if best_q is None:
        return FtResult(score=FNUL, detail=None)
    return FtResult(score=best, detail=None, query=best_q, candidate=best_c)
