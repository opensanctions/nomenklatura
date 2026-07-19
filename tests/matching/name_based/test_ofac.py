import csv
from pathlib import Path

from followthemoney import ValueEntity as Entity

from nomenklatura.matching.name_based.ofac import ofac_name_score
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

FIXTURES = Path(__file__).parent / "ofac_fixtures.csv"
config = ScoringConfig.defaults()


def _load_fixtures():
    with FIXTURES.open() as fh:
        for row in csv.DictReader(fh):
            yield row["query_name"], row["result_name"], int(row["ofac_score"])


def test_ofac_score_exact():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    res = ofac_name_score(a, b, config)
    assert res.score == 1.0
    # whole-string rejected by the first-letter gate (V vs P);
    # per-token is perfect on both tokens and carries the score.
    assert res.detail == "whole-string=0.00, per-token=1.00"


def test_ofac_score_first_letter_gate():
    """whole-string is rejected (B != G); per-token averages a zeroed
    BUSH<->HASWANI pair (JW=0.46 < PER_PAIR_JW_FLOOR) with a perfect
    GEORGE<->George - the floor mechanism documented in
    `_per_token_score`."""
    a = e("Person", name="GEORGE BUSH")
    b = e("Person", name="HASWANI, George")
    res = ofac_name_score(a, b, config)
    assert res.score == 0.5
    assert res.detail == "whole-string=0.00, per-token=0.50"


def test_ofac_score_token_order_asymmetry():
    """The first-letter gate in `_whole_string_score` keys on the
    user-typed string's first character, not a letter set - so token
    order matters."""
    b = e("Person", name="GEORGIOU, Georgios")
    forward = ofac_name_score(e("Person", name="GEORGE BUSH"), b, config)
    reversed_ = ofac_name_score(e("Person", name="BUSH GEORGE"), b, config)
    # Forward: whole-string fires (G == G) and carries the score; per-token
    # is the same as reversed (mean is token-order-insensitive).
    assert forward.score >= 0.8
    assert forward.detail == "whole-string=0.85, per-token=0.45"
    # Reversed: whole-string rejected (B vs G); only per-token contributes.
    assert reversed_.score < 0.8
    assert reversed_.detail == "whole-string=0.00, per-token=0.45"


def test_ofac_score_short_token_dropped():
    """`UN` is below `SHORT_TOKEN_MAX_LEN` and gets dropped by
    `_drop_short_tokens`, so the query collapses to KIM JONG."""
    a = e("Person", name="KIM JONG UN")
    res_un = ofac_name_score(a, e("Person", name="KIM, Jong Un"), config)
    res_man = ofac_name_score(a, e("Person", name="KIM, Jong Man"), config)
    assert res_un.score == 1.0
    assert res_un.detail == "whole-string=1.00, per-token=1.00"
    # per-token still scores 1.0 (UN dropped, KIM+JONG match perfectly);
    # whole-string takes a small hit for the UN/MAN suffix difference.
    assert res_man.score == 1.0
    assert res_man.detail == "whole-string=0.95, per-token=1.00"


def test_ofac_score_single_char_query_kept():
    """The drop-short safety: don't empty the input list. The 0.74
    score is a property of Jaro-Winkler on single-char queries (two
    of the three terms in Jaro's formula reach 1.0 when m/|query|=1),
    not an OFAC-specific behaviour."""
    a = e("Person", name="Z")
    b = e("Person", name="ZOLLNER")
    res = ofac_name_score(a, b, config)
    assert res.score > 0
    assert res.detail == "whole-string=0.74, per-token=0.74"


def test_ofac_score_fixture_positive_parity():
    """Aggregate parity: on positive fixture rows (OFAC reported a
    score), at least 90% must land within +/-5 points and mean |delta|
    must be <= 2. The bar is slightly looser than the module-level
    claim (95.7% / 1.5) to leave room for SDN list drift."""
    deltas = []
    for query, candidate, expected in _load_fixtures():
        if expected < 0:
            continue
        a = e("Person", name=query)
        b = e("Person", name=candidate)
        got = round(ofac_name_score(a, b, config).score * 100)
        deltas.append(abs(got - expected))
    within_5 = sum(1 for d in deltas if d <= 5)
    mean_abs = sum(deltas) / len(deltas)
    assert within_5 / len(deltas) >= 0.90, (
        f"only {within_5}/{len(deltas)} within +/-5"
    )
    assert mean_abs <= 2.0, f"mean |delta| = {mean_abs:.2f}"


def test_ofac_score_fixture_negative_threshold():
    """Negative rows are encoded as -1 ("did not appear at slider 80").
    Most must score below the 80 slider; tolerate one over-fire to
    accommodate known tokenisation edges."""
    below = 0
    total = 0
    for query, candidate, expected in _load_fixtures():
        if expected != -1:
            continue
        total += 1
        a = e("Person", name=query)
        b = e("Person", name=candidate)
        if ofac_name_score(a, b, config).score < 0.8:
            below += 1
    assert below >= total - 1, f"{below}/{total} below the 80 slider"


def test_ofac_name_score_entity_pair():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    res = ofac_name_score(a, b, config)
    assert res.score == 1.0
    assert res.query == "VLADIMIR PUTIN"
    assert res.candidate == "PUTIN, Vladimir"
    # First-letter gate rejects V vs P, so whole-string is 0; per-token
    # is 1.00 (perfect token match) and carries the score.
    assert res.detail == "whole-string=0.00, per-token=1.00"


def test_ofac_name_score_detail_per_token_floor():
    """The per-pair JW < 0.5 floor zeroes the BUSH<->HASWANI pair;
    GEORGE pairs perfectly with George. Mean of (1.0, 0.0) = 0.5."""
    a = e("Person", name="GEORGE BUSH")
    b = e("Person", name="HASWANI, George")
    res = ofac_name_score(a, b, config)
    assert res.score == 0.5
    assert res.detail == "whole-string=0.00, per-token=0.50"


def test_ofac_name_score_alias_aware():
    """Multiple candidate names: take the best pair."""
    a = e("Person", name="VLADIMIR PUTIN")
    data = {
        "id": "ent",
        "schema": "Person",
        "properties": {"name": ["Some Other Person", "PUTIN, Vladimir"]},
    }
    b = Entity.from_dict(data)
    res = ofac_name_score(a, b, config)
    assert res.score == 1.0
    assert res.candidate == "PUTIN, Vladimir"
    # detail describes the winning pair, not the losing alias.
    assert res.detail == "whole-string=0.00, per-token=1.00"


def test_ofac_name_score_empty():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person")
    res = ofac_name_score(a, b, config)
    assert res.score == 0.0
    # No pair scored, no detail to surface.
    assert res.detail is None
