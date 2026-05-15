import csv
from pathlib import Path

from followthemoney import ValueEntity as Entity

from nomenklatura.matching import OFACMatcher
from nomenklatura.matching.name_based.ofac import ofac_score, ofac_name_score
from nomenklatura.matching.types import ScoringConfig

from .util import e

FIXTURES = Path(__file__).parent / "ofac_fixtures.csv"
config = ScoringConfig.defaults()


def _load_fixtures():
    with FIXTURES.open() as fh:
        for row in csv.DictReader(fh):
            yield row["query_name"], row["result_name"], int(row["ofac_score"])


def test_ofac_score_exact():
    assert ofac_score("VLADIMIR PUTIN", "PUTIN, Vladimir") == 100


def test_ofac_score_first_letter_gate():
    # T1 rejects (B != G), T2 averages a 0 in (BUSH<->HASWANI < 0.5):
    # the load-bearing quirk that demotes "George Bush"-style false friends.
    assert ofac_score("GEORGE BUSH", "HASWANI, George") < 80


def test_ofac_score_token_order_asymmetry():
    # T1's first-letter gate is on the user-typed string, not a letter set.
    assert ofac_score("GEORGE BUSH", "GEORGIOU, Georgios") >= 80
    assert ofac_score("BUSH GEORGE", "GEORGIOU, Georgios") < 80


def test_ofac_score_short_token_dropped():
    # "UN" (<=2 chars) is dropped from the input, so KIM JONG matches
    # multiple Kim Jong-* individuals at 100.
    assert ofac_score("KIM JONG UN", "KIM, Jong Un") == 100
    assert ofac_score("KIM JONG UN", "KIM, Jong Man") == 100


def test_ofac_score_single_char_query_kept():
    # The drop-short safety: don't empty the input list.
    assert ofac_score("Z", "ZOLLNER") > 0


def test_ofac_score_fixture_positive_parity():
    """Aggregate parity: on positive fixture rows (OFAC reported a
    score), at least 90% must land within +/-5 points and mean |delta|
    must be <= 2. The plan documents 95.7% / 1.49 on the full fixture;
    we set the bar slightly looser to leave room for SDN list drift."""
    deltas = []
    for query, candidate, expected in _load_fixtures():
        if expected < 0:
            continue
        got = ofac_score(query, candidate)
        deltas.append(abs(got - expected))
    within_5 = sum(1 for d in deltas if d <= 5)
    mean_abs = sum(deltas) / len(deltas)
    assert within_5 / len(deltas) >= 0.90, (
        f"only {within_5}/{len(deltas)} within +/-5"
    )
    assert mean_abs <= 2.0, f"mean |delta| = {mean_abs:.2f}"


def test_ofac_score_fixture_negative_threshold():
    """Negative rows are encoded as -1 ("did not appear at slider 80").
    Plan says 5 of 6 must score below the 80 slider; the one allowed
    over-fire is ALQAEDA -> AL QAEDA, a documented tokenisation edge."""
    below = 0
    total = 0
    for query, candidate, expected in _load_fixtures():
        if expected != -1:
            continue
        total += 1
        if ofac_score(query, candidate) < 80:
            below += 1
    assert below >= total - 1, f"{below}/{total} below the 80 slider"


def test_ofac_name_score_entity_pair():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    res = ofac_name_score(a, b, config)
    assert res.score == 1.0
    assert res.query == "VLADIMIR PUTIN"
    assert res.candidate == "PUTIN, Vladimir"


def test_ofac_name_score_alias_aware():
    # Multiple candidate names: take the best pair.
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


def test_ofac_name_score_empty():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person")
    assert ofac_name_score(a, b, config).score == 0.0


def test_ofac_matcher_compare():
    a = e("Person", name="VLADIMIR PUTIN")
    b = e("Person", name="PUTIN, Vladimir")
    assert OFACMatcher.compare(a, b, config).score == 1.0

    b = e("Person", name="HASWANI, George")
    assert OFACMatcher.compare(a, b, config).score < 0.8


def test_ofac_matcher_name_only():
    # Name-only by FAQ 251: DOB / country mismatches do not affect the score.
    a = e("Person", name="VLADIMIR PUTIN", birthDate="1952-10-07", country="ru")
    b = e("Person", name="PUTIN, Vladimir", birthDate="1980-01-01", country="us")
    assert OFACMatcher.compare(a, b, config).score == 1.0
