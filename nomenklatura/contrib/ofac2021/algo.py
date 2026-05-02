"""A minimal reproduction of OFAC's Sanctions List Search scoring.

Reverse-engineered from the public tool at
`sanctionssearch.ofac.treas.gov` plus FAQ 249. Tracks OFAC's reported
score within ±5 points on 95.7% of a 164-row parity fixture (see
`fixtures.csv` and `compare.py`); mean absolute error 1.5 points.

This is not a "good" name matcher in the academic sense — it
inherits OFAC's quirks (single-token explosions, length-asymmetric
behavior, the per-pair JW < 0.5 cliff). For a recall-vs-precision
calibrated screener, see `nomenklatura.matching.logic_v2`. This
module exists so customers can self-serve "what would OFAC say
about this name?" without round-tripping to treasury.gov.

Three mechanisms each match an observed quirk:

1. **Whole-string JW gated by first-letter** (`_t1`). The
   `BUSH GEORGE` query returns 0 hits while `GEORGE BUSH` returns 3
   — same tokens, reversed order. So OFAC's whole-string match is
   gated on the literal `input[0] == candidate[0]`.

2. **Jaro-Winkler without the 0.7 boost threshold** (`_jw`). The
   1990 Winkler paper recommends only applying the prefix bonus
   when pure Jaro ≥ 0.7. Modern Python libs (rapidfuzz, jellyfish)
   honour that threshold. The classic SimMetrics-Java library does
   not — it applies the bonus unconditionally. OFAC's front end is
   ASP.NET WebForms with AjaxControlToolkit (vintage 2008-2012 .NET
   3.5/4.0 stack), so SimMetrics-style is the most likely JW their
   contractor reached for. This single change recovers the long-
   candidate cluster (`VLADIMIR PUTIN ↔ VLADIMIROVKA ADVANCED
   WEAPONS AND RESEARCH COMPLEX` 82 vs rapidfuzz 64).

3. **Per-input-token best-pairing JW with a 0.5 floor** (`_t2`).
   `GEORGE BUSH ↔ HASWANI, George` scores 50 in OFAC (a perfect
   GEORGE-George match averaged with a near-zero BUSH-HASWANI). A
   simple mean would give 73; zeroing the BUSH-HASWANI pair
   (JW = 0.46 < 0.5) gives 50 exactly. Combined with dropping
   ≤2-char input tokens (with single-token safety), this also
   resolves the KIM JONG UN case where OFAC matches 5 different
   individuals at 100.

The score is `max(T1, T2)` per FAQ 249.
"""

from rapidfuzz.distance import Jaro, JaroWinkler
from rigour.names import tokenize_name


# Tuned against the 164-row positive fixture in fixtures.csv. Each
# constant resolves at least one observable OFAC quirk.
PAIR_FLOOR = 0.5         # per-pair JW < this contributes 0 to T2
MIN_TOKEN_LEN = 2        # input tokens ≤ this are dropped (with safety)
WINKLER_PREFIX_MAX = 4   # standard Winkler prefix cap (1990 paper)
WINKLER_WEIGHT = 0.1     # standard Winkler scaling factor (1990 paper)


def _jw(a: str, b: str) -> float:
    """SimMetrics-style Jaro-Winkler: prefix bonus applied
    unconditionally (no 0.7 boost threshold). See module docstring
    for why this matches OFAC where rapidfuzz's standard JW does
    not."""
    if not a or not b:
        return 0.0
    j = Jaro.similarity(a, b)
    if j == 0.0:
        return 0.0
    p = 0
    for ca, cb in zip(a[:WINKLER_PREFIX_MAX], b[:WINKLER_PREFIX_MAX]):
        if ca == cb:
            p += 1
        else:
            break
    return j + p * WINKLER_WEIGHT * (1 - j)


def _tokens(s: str) -> list[str]:
    """Tokenise via rigour's Unicode-aware splitter, then uppercase.
    Apostrophes / commas / periods are deleted (combining-mark
    category), not split on — `O'BRIEN` stays one token."""
    return [t.upper() for t in tokenize_name(s)]


def _drop_short(toks: list[str]) -> list[str]:
    """Strip tokens shorter than MIN_TOKEN_LEN, but never empty the
    list — a single-char query like `Z` keeps its lone token."""
    kept = [t for t in toks if len(t) > MIN_TOKEN_LEN]
    return kept or toks


def _t1(query: str, candidate: str) -> float:
    """Whole-string JW (no-threshold variant), gated by
    `input[0] == candidate[0]`."""
    q = " ".join(_tokens(query))
    c = " ".join(_tokens(candidate))
    if not q or not c or q[0] != c[0]:
        return 0.0
    return _jw(q, c)


def _t2(query: str, candidate: str) -> float:
    """Per-input-token best-pairing JW, mean over input tokens. Pairs
    with JW < `PAIR_FLOOR` contribute 0 to the mean — the soft
    first-letter check that's implicit in JW magnitude. Per-token
    comparisons rarely fall below the 0.7 Jaro floor, so rapidfuzz's
    standard JW is fine here."""
    q_toks = _drop_short(_tokens(query))
    c_toks = _tokens(candidate)
    if not q_toks or not c_toks:
        return 0.0
    pair_scores = []
    for qt in q_toks:
        best = max((JaroWinkler.similarity(qt, ct) for ct in c_toks), default=0.0)
        pair_scores.append(best if best >= PAIR_FLOOR else 0.0)
    return sum(pair_scores) / len(pair_scores)


def ofac_score(query: str, candidate: str) -> int:
    """Approximate OFAC's Sanctions List Search score for a `query`
    name against a `candidate` name on the SDN list. Returns an
    integer 0–100 mirroring OFAC's slider scale.

    Tracks OFAC's reported score within ±5 points on 95.7% of a
    164-row parity fixture; mean absolute error 1.5 points. Does not
    reproduce alias-aware scoring (OFAC scores against the best of
    an entity's aliases; this function scores against one
    alias-string at a time)."""
    return round(max(_t1(query, candidate), _t2(query, candidate)) * 100)
