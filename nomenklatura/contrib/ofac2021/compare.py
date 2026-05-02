"""Score the OFAC parity fixtures against candidate algorithms.

Reads `fixtures.csv` — `(query, candidate, ofac_score)` triples captured
from `sanctionssearch.ofac.treas.gov`. `ofac_score = -1` is the
sentinel for "did not appear at slider 80" (i.e., OFAC's score for
this pair is below 80 — exact value unknown). Numeric agreement is
measured on positive rows; threshold-pass rate is measured on the
negatives.

Each scorer is a hypothesis about how OFAC's algorithm composes the
two FAQ-249 techniques. Three finalists kept after culling:

    faq249_d2    : max(T1 first-letter-gated, T2 mean over input
                   tokens). Drops input tokens of ≤2 chars (with
                   single-token protection) before averaging — the
                   KIM JONG UN fix.
    faq249_thr   : faq249_d2 + per-pair JW < 0.5 zeroed before mean.
                   The HASWANI George fix without breaking
                   PUTIN ↔ TURIN.
    faq249_trunc : faq249_thr + T1 truncates the candidate to input
                   length when the candidate is longer. The
                   long-candidate fix (VLADIMIROV / VLADIMIROVKA /
                   GEORGIEVA cluster).

Run:
    python -m nomenklatura.contrib.ofac2021.compare
"""

import csv
from pathlib import Path
from statistics import mean

from rapidfuzz.distance import Jaro, JaroWinkler
from rigour.names import tokenize_name


FIXTURE = Path(__file__).parent / "fixtures.csv"
SLIDER = 80  # the slider setting captures were taken at
MIN_TOKEN_LEN = 2  # input tokens shorter than this are dropped
PAIR_FLOOR = 0.5  # per-pair JW below this contributes 0 to the mean


def tokens(s: str) -> list[str]:
    """Tokenise via rigour's Unicode-aware tokeniser, then uppercase.
    Apostrophes / commas / periods are *deleted* (combining-mark
    category), not split on — `O'BRIEN` is one token, not two."""
    return [t.upper() for t in tokenize_name(s)]


def normalise(s: str) -> str:
    return " ".join(tokens(s))


def _drop_short(toks: list[str], min_len: int) -> list[str]:
    """Strip tokens shorter than `min_len`, but never empty the list —
    a single-char query like `Z` keeps its lone token."""
    kept = [t for t in toks if len(t) > min_len]
    return kept or toks


TRUNC_RATIO = 2.0  # truncate candidate when len(c) / len(q) > this


def _jw_no_threshold(a: str, b: str) -> float:
    """JW with prefix bonus applied unconditionally (no 0.7 boost
    threshold). Matches SimMetrics-Java behavior — the dominant
    similarity library in 2008-2012 .NET data-quality stacks."""
    if not a or not b:
        return 0.0
    j = Jaro.similarity(a, b)
    if j == 0.0:
        return 0.0
    p = 0
    for ca, cb in zip(a[:4], b[:4]):
        if ca == cb:
            p += 1
        else:
            break
    return j + p * 0.1 * (1 - j)


def _t1(query: str, candidate: str, *, truncate: bool = False) -> int:
    """Whole-string Jaro-Winkler, gated by input[0] == candidate[0].
    With `truncate=True`, a candidate that's >2× the input length is
    capped at input length — neutralises Jaro's `m / c_len` term that
    drags scores on long-tail candidates like 'VLADIMIROVKA ADVANCED
    WEAPONS AND RESEARCH COMPLEX'. Below the 2× ratio, plain JW; the
    threshold avoids over-firing on near-equal-length candidates with
    accidental prefix similarity (e.g., GEORGE BUSH ↔ GOOBE Suleiman
    Daoud)."""
    q, c = normalise(query), normalise(candidate)
    if not q or not c or q[0] != c[0]:
        return 0
    if truncate and len(c) / max(len(q), 1) > TRUNC_RATIO:
        c = c[: len(q)]
    return round(JaroWinkler.similarity(q, c) * 100)


def _t2(
    query: str,
    candidate: str,
    *,
    floor: float = 0.0,
) -> int:
    """Per-input-token best-pairing JW, averaged. Pair scores below
    `floor` are zeroed before averaging — what zeroes the BUSH-vs-
    HASWANI part of GEORGE BUSH ↔ HASWANI, George (JW = 0.46) so the
    composite collapses to 50, matching OFAC."""
    q_toks = _drop_short(tokens(query), MIN_TOKEN_LEN)
    c_toks = tokens(candidate)
    if not q_toks or not c_toks:
        return 0
    pair_scores = []
    for qt in q_toks:
        best = max((JaroWinkler.similarity(qt, ct) for ct in c_toks), default=0.0)
        pair_scores.append(best if best >= floor else 0.0)
    return round(mean(pair_scores) * 100)


def faq249_d2(query: str, candidate: str) -> int:
    return max(_t1(query, candidate), _t2(query, candidate))


def faq249_thr(query: str, candidate: str) -> int:
    return max(_t1(query, candidate), _t2(query, candidate, floor=PAIR_FLOOR))


def faq249_trunc(query: str, candidate: str) -> int:
    return max(
        _t1(query, candidate, truncate=True),
        _t2(query, candidate, floor=PAIR_FLOOR),
    )


def faq249_simjw(query: str, candidate: str) -> int:
    """SimMetrics-style: T1 uses no-threshold JW (prefix bonus applies
    unconditionally), no truncation needed. T2 unchanged."""
    q = normalise(query)
    c = normalise(candidate)
    if q and c and q[0] == c[0]:
        t1 = round(_jw_no_threshold(q, c) * 100)
    else:
        t1 = 0
    return max(t1, _t2(query, candidate, floor=PAIR_FLOOR))


SCORERS = {
    "faq249_d2": faq249_d2,
    "faq249_thr": faq249_thr,
    "faq249_trunc": faq249_trunc,
    "faq249_simjw": faq249_simjw,
}


def main() -> None:
    rows = list(csv.DictReader(FIXTURE.open()))
    pos = [r for r in rows if int(r["ofac_score"]) >= 0]
    neg = [r for r in rows if int(r["ofac_score"]) < 0]

    headers = ["query", "candidate", "ofac"] + list(SCORERS) + [
        f"Δ{n}" for n in SCORERS
    ]
    widths = [28, 44, 4] + [9] * len(SCORERS) + [6] * len(SCORERS)

    def fmt(cells: list[str]) -> str:
        return " | ".join(c.ljust(w)[:w] for c, w in zip(cells, widths))

    print(fmt(headers))
    print("-" * (sum(widths) + 3 * (len(widths) - 1)))

    deltas: dict[str, list[int]] = {n: [] for n in SCORERS}
    fp: dict[str, int] = {n: 0 for n in SCORERS}  # false positives on negatives

    for r in rows:
        ofac = int(r["ofac_score"])
        cells = [r["query_name"], r["result_name"], "<80" if ofac < 0 else str(ofac)]
        scores = {n: f(r["query_name"], r["result_name"]) for n, f in SCORERS.items()}
        for n in SCORERS:
            cells.append(str(scores[n]))
        for n in SCORERS:
            if ofac < 0:
                cells.append("FP" if scores[n] >= SLIDER else "ok")
                if scores[n] >= SLIDER:
                    fp[n] += 1
            else:
                d = scores[n] - ofac
                deltas[n].append(d)
                cells.append(f"{d:+d}")
        print(fmt(cells))

    print()
    print(f"Positive fixtures (numeric agreement): {len(pos)}")
    print(f"  {'scorer':<14}  {'mean Δ':>7}  {'mean |Δ|':>9}  "
          f"{'within±5':>8}  {'over+5':>6}  {'under-5':>7}")
    for n, ds in deltas.items():
        abs_ds = [abs(d) for d in ds]
        within = sum(1 for d in ds if abs(d) <= 5)
        over = sum(1 for d in ds if d > 5)
        under = sum(1 for d in ds if d < -5)
        print(f"  {n:<14}  {mean(ds):+7.1f}  {mean(abs_ds):9.2f}  "
              f"{within:8d}  {over:6d}  {under:7d}")

    print()
    print(f"Negative fixtures (should score < {SLIDER}): {len(neg)}")
    print(f"  {'scorer':<14}  {'false positives':>16}")
    for n in SCORERS:
        print(f"  {n:<14}  {fp[n]:>3} / {len(neg)}")


if __name__ == "__main__":
    main()
