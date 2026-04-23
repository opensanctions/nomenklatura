from pathlib import Path
from typing import List

from rigour.names import Name, NameTypeTag, analyze_names
from rigour.text.scripts import common_scripts

from nomenklatura.matching.logic_v2.names.analysis import names_product


FIXTURE = Path(__file__).parent.parent / "fixtures" / "putin_names.txt"


def _load_fixture_names() -> List[Name]:
    lines = [ln.strip() for ln in FIXTURE.read_text().splitlines() if ln.strip()]
    return list(analyze_names(NameTypeTag.PER, lines, consolidate=False))


def _pair_is_justified(q: Name, r: Name) -> bool:
    if common_scripts(q.comparable, r.comparable):
        return True
    return bool(set(q.symbols) & set(r.symbols))


def test_names_product_empty_inputs():
    rs = set(
        analyze_names(
            NameTypeTag.PER,
            ["John Smith", "Jane Doe"],
            consolidate=False,
        )
    )
    qs = set(analyze_names(NameTypeTag.PER, ["Vladimir Putin"], consolidate=False))
    assert list(names_product(set(), rs)) == []
    assert list(names_product(qs, set())) == []
    assert list(names_product(set(), set())) == []


def test_names_product_numeric_symbol_rescue_without_script():
    # Numeric-only names have no "real" Unicode script, so the script
    # gate never fires — the NUMERIC symbol overlap is the only thing
    # keeping pairs alive. Candidates without a matching numeric are
    # dropped even though they share Latin script among themselves.
    queries = set(analyze_names(NameTypeTag.OBJ, ["007"], consolidate=False))
    results = set(
        analyze_names(
            NameTypeTag.OBJ,
            [
                "Agent 007",
                "Team 7",
                "Squadron 7",
                "Unit 42",
                "Some Unit",
                "Other Agent",
                "Agent Smith",
            ],
            consolidate=False,
        )
    )
    assert len(queries) * len(results) > 6  # past the small-product shortcut
    pairs = list(names_product(queries, results))
    kept = {r.comparable for _, r in pairs}
    assert kept == {"agent 7", "team 7", "squadron 7"}
    for q, r in pairs:
        assert not common_scripts(q.comparable, r.comparable)
        assert set(q.symbols) & set(r.symbols)


def test_names_product_small_product_yields_all():
    # Products with 6 or fewer pairs bypass the pruning entirely.
    qs = set(analyze_names(NameTypeTag.PER, ["Vladimir Putin"], consolidate=False))
    rs = set(
        analyze_names(
            NameTypeTag.PER,
            ["John Smith", "Jane Doe", "Alice Jones"],
            consolidate=False,
        )
    )
    pairs = list(names_product(qs, rs))
    assert len(pairs) == len(qs) * len(rs) == 3


def test_names_product_putin_prunes_cartesian():
    results = set(_load_fixture_names())
    queries = set(
        analyze_names(
            NameTypeTag.PER,
            ["Vladimir Putin", "Владимир Путин", "விளாடிமிர் புடின்"],
            consolidate=False,
        )
    )
    pairs = list(names_product(queries, results))
    cartesian = len(queries) * len(results)
    assert cartesian > 6  # guards against the small-product shortcut
    assert len(pairs) < cartesian
    for q, r in pairs:
        assert _pair_is_justified(q, r), (q.original, r.original)


def test_names_product_latin_query_script_matches_latin_candidates():
    # A Latin query should share script with every Latin fixture entry,
    # so every Latin-script pair survives via the script gate.
    results = set(_load_fixture_names())
    queries = set(
        analyze_names(NameTypeTag.PER, ["Vladimir Putin"], consolidate=False)
    )
    (query,) = queries
    pairs = list(names_product(queries, results))
    kept = {r for _, r in pairs}
    for r in results:
        if common_scripts(query.comparable, r.comparable):
            assert r in kept, r.original


def test_names_product_cyrillic_query_latinised_comparable():
    # Name.comparable is transliterated, so a Cyrillic query lands in Latin
    # script for comparison — the script gate still fires against Latin
    # candidates.
    results = set(_load_fixture_names())
    queries = set(
        analyze_names(NameTypeTag.PER, ["Владимир Путин"], consolidate=False)
    )
    (query,) = queries
    assert common_scripts(query.comparable, "vladimir")
    pairs = list(names_product(queries, results))
    # At least every Latin candidate should be kept via script overlap.
    latin_candidates = [
        r for r in results if common_scripts("vladimir", r.comparable)
    ]
    kept_comparables = {r.comparable for _, r in pairs}
    for r in latin_candidates:
        assert r.comparable in kept_comparables, r.original


def test_names_product_unknown_script_without_aliases_yields_nothing():
    # A real Putin rendering in Tamil script has no Wikidata alias in
    # rigour's tagger, so the query carries no NAME symbols. It also
    # shares no script with any fixture candidate — the pruner should
    # drop the entire cross product.
    results = set(_load_fixture_names())
    queries = set(
        analyze_names(NameTypeTag.PER, ["விளாடிமிர் புடின்"], consolidate=False)
    )
    (query,) = queries
    assert len(query.symbols) == 0
    for r in results:
        assert not common_scripts(query.comparable, r.comparable)
    assert list(names_product(queries, results)) == []


def test_names_product_partial_alias_rescues_via_symbol_overlap():
    # A Thai rendering of Putin carries a partial alias set (KHUYLO but
    # not the full Q-ID fan-out), so the script gate fails everywhere
    # and only symbol-overlap candidates survive.
    results = set(_load_fixture_names())
    queries = set(
        analyze_names(NameTypeTag.PER, ["วลาดิเมียร์ ปูติน"], consolidate=False)
    )
    (query,) = queries
    assert query.symbols, "expected at least one NAME alias for Thai Putin"
    for r in results:
        assert not common_scripts(query.comparable, r.comparable)
    pairs = list(names_product(queries, results))
    assert 0 < len(pairs) < len(results)
    for q, r in pairs:
        assert set(q.symbols) & set(r.symbols)


def test_names_product_same_script_dominates_cross_script():
    # When a same-script candidate's symbol overlap already covers a
    # cross-script candidate's overlap, the cross-script pair is pruned.
    # Motivating case (issue #248): a Latin query against an entity
    # carrying both a Latin and an Arabic rendering of the same surname.
    # With equal symbolic evidence on both sides, the Latin pair is the
    # better witness and the Arabic pair is dropped before scoring.
    queries = set(
        analyze_names(NameTypeTag.PER, ["Fernando Perez"], consolidate=False)
    )
    results = set(
        analyze_names(
            NameTypeTag.PER,
            [
                "Fernando Perez Royo",
                "فرناندو بيريز",
                # Padding to clear the 6-pair small-product shortcut.
                "Alice Johnson",
                "Bob Smith",
                "Carol Davis",
                "Dave Wilson",
                "Eve Brown",
            ],
            consolidate=False,
        )
    )
    assert len(queries) * len(results) > 6
    (query,) = queries
    latin = next(r for r in results if r.comparable == "fernando perez royo")
    arabic = next(r for r in results if r.comparable == "فرناندو بيريز")
    # Sanity: latin shares script, arabic doesn't, and their overlaps
    # with the query are equal — the exact precondition the rule targets.
    assert common_scripts(query.comparable, latin.comparable)
    assert not common_scripts(query.comparable, arabic.comparable)
    assert (set(query.symbols) & set(latin.symbols)) == (
        set(query.symbols) & set(arabic.symbols)
    )
    pairs = list(names_product(queries, results))
    kept = {r for _, r in pairs}
    assert latin in kept
    assert arabic not in kept


def test_names_product_cross_script_adds_new_evidence_survives():
    # The same-script dominance rule only prunes when the cross-script
    # pair adds nothing new. A cross-script candidate carrying a symbol
    # the same-script pair doesn't should still survive.
    queries = set(
        analyze_names(NameTypeTag.PER, ["Fernando Perez"], consolidate=False)
    )
    # "Fernando" in Cyrillic has Latin-transliterated comparable, so it
    # still lands in the shared-script bucket; pair it with a richer
    # Arabic name that carries an extra symbol.
    results = set(
        analyze_names(
            NameTypeTag.PER,
            [
                "Fernando",
                "فرناندو بيريز",
                "Alice Johnson",
                "Bob Smith",
                "Carol Davis",
                "Dave Wilson",
                "Eve Brown",
            ],
            consolidate=False,
        )
    )
    assert len(queries) * len(results) > 6
    (query,) = queries
    latin = next(r for r in results if r.comparable == "fernando")
    arabic = next(r for r in results if r.comparable == "فرناندو بيريز")
    latin_overlap = set(query.symbols) & set(latin.symbols)
    arabic_overlap = set(query.symbols) & set(arabic.symbols)
    assert latin_overlap < arabic_overlap  # arabic adds new evidence
    pairs = list(names_product(queries, results))
    kept = {r for _, r in pairs}
    assert latin in kept
    assert arabic in kept  # survives because it carries new symbolic evidence


def test_names_product_symbol_dominance_drops_strict_subsets():
    # Force a no-script-overlap setup so the dominance rule kicks in:
    # a Cyrillic query against two Arabic candidates where one candidate
    # carries a superset of the other's NAME symbols. The dominated one
    # should be pruned.
    results = set(_load_fixture_names())
    # Pad with extras so we stay above the small-product shortcut.
    queries = set(
        analyze_names(
            NameTypeTag.PER,
            [
                "Владимир Путин",
                "Владимир Владимирович Путин",
                "В. В. Путин",
            ],
            consolidate=False,
        )
    )
    pairs = list(names_product(queries, results))
    # Invariant: no kept pair's symbol overlap is a strict subset of
    # another kept pair's overlap for the same query (only applies to
    # the non-script-sharing bucket).
    by_query = {}
    for q, r in pairs:
        if common_scripts(q.comparable, r.comparable):
            continue
        by_query.setdefault(q, []).append(set(q.symbols) & set(r.symbols))
    for overlaps in by_query.values():
        for ov in overlaps:
            assert not any(ov < other for other in overlaps)
