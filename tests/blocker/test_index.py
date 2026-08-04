import math
import pytest
from pathlib import Path
from followthemoney import Dataset, StatementEntity

from nomenklatura.blocker.index import DEFAULT_MAX_BUCKET_SIZE, Index
from nomenklatura.blocker.tokenizer import tokenize_entity
from nomenklatura.resolver.identifier import Identifier
from nomenklatura.resolver.linker import Linker
from nomenklatura.store import SimpleMemoryStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
VERBAND_ID = "62ad0fe6f56dbbf6fee57ce3da76e88c437024d5"
VERBAND_BADEN_ID = "69401823a9f0a97cfdc37afa7c3158374e007669"
VERBAND_BADEN_DATA = {
    "id": "bla",
    "schema": "Company",
    "properties": {
        "name": ["VERBAND DER METALL UND ELEKTROINDUSTRIE BADEN WURTTEMBERG"]
    },
}


def make_manual_index(
    index_path: Path,
    dstore: SimpleMemoryStore,
    entries: list[tuple[str, str, str, str, int]],
    schemata: list[tuple[str, str]],
    max_bucket_size: int,
    options: dict[str, object] | None = None,
) -> Index:
    index = Index(
        dstore.default_view(),
        index_path,
        options={"max_bucket_size": max_bucket_size, **(options or {})},
    )
    index.con.execute("""
        CREATE OR REPLACE TABLE entries
            (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
    """)
    index.con.executemany("INSERT INTO entries VALUES (?, ?, ?, ?, ?)", entries)
    index.con.execute("""CREATE OR REPLACE TABLE schemata ("left" TEXT, "right" TEXT)""")
    index.con.executemany("INSERT INTO schemata VALUES (?, ?)", schemata)
    return index


def run_matching(
    index: Index,
    matching_rows: list[tuple[str, str, str, str, int]],
    boosts: dict[str, float] | None = None,
) -> dict[str, list[tuple[str, float]]]:
    """Run the matching query path over manually inserted subject rows."""
    index.con.execute("CREATE OR REPLACE TABLE boosts (field TEXT, boost FLOAT)")
    for field, boost in (boosts or {}).items():
        index.con.execute("INSERT INTO boosts VALUES (?, ?)", [field, boost])
    index._build_frequencies()
    index.con.execute("""
        CREATE OR REPLACE TABLE matching
            (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
    """)
    index.con.executemany("INSERT INTO matching VALUES (?, ?, ?, ?, ?)", matching_rows)
    index._build_matching_stopwords()
    index._apply_stopwords(
        "matching",
        "matching_filtered",
        stopwords_table="matching_stopwords",
    )
    return {
        str(subject): [(str(match_id), score) for match_id, score in candidates]
        for subject, candidates in index._find_matches()
    }


def test_max_bucket_size_configures_pair_cost_caps(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = Index(
        dstore.default_view(),
        index_path,
        options={"max_bucket_size": 4},
    )
    try:
        assert index.max_bucket_size == 4
        assert index.max_pair_cost == 6
        assert index.max_match_pair_cost == 16
    finally:
        index.close()


def test_default_max_bucket_size_configures_pair_cost_caps(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = Index(dstore.default_view(), index_path)
    try:
        assert index.max_bucket_size == DEFAULT_MAX_BUCKET_SIZE
        assert (
            index.max_pair_cost
            == DEFAULT_MAX_BUCKET_SIZE * (DEFAULT_MAX_BUCKET_SIZE - 1) // 2
        )
        assert index.max_match_pair_cost == DEFAULT_MAX_BUCKET_SIZE**2
    finally:
        index.close()


def test_max_bucket_size_rejects_negative_values(
    index_path: Path, dstore: SimpleMemoryStore
):
    try:
        Index(
            dstore.default_view(),
            index_path,
            options={"max_bucket_size": -1},
        )
    except ValueError as exc:
        assert str(exc) == "max_bucket_size must be >= 0"
    else:
        raise AssertionError("expected max_bucket_size to reject negative values")


def test_index_build(index_path: Path, dstore: SimpleMemoryStore):
    index = Index(dstore.default_view(), index_path)
    assert index.entity_count("entries") == 0
    index.build()
    assert index.entity_count("entries") == 184
    assert index._has_table("term_frequencies_all")
    assert not index._has_table("stopwords")
    assert not index._has_table("entries_filtered")


def test_index_pairs(dstore: SimpleMemoryStore, dindex: Index):
    view = dstore.default_view()
    assert not dindex._has_table("stopwords")
    assert not dindex._has_table("entries_filtered")
    pairs = list(dindex.pairs())
    assert dindex._has_table("stopwords")
    assert dindex._has_table("entries_filtered")

    # At least one pair is found
    assert len(pairs) > 0, len(pairs)

    # A pair has tokens which overlap
    pair, score = pairs[0]
    entity0 = view.get_entity(str(pair[0]))
    assert entity0 is not None
    tokens0 = set(tokenize_entity(entity0))
    entity1 = view.get_entity(str(pair[1]))
    assert entity1 is not None
    tokens1 = set(tokenize_entity(entity1))
    overlap = tokens0.intersection(tokens1)
    assert len(overlap) > 0, overlap

    # A pair has non-zero score
    assert score > 0
    # pairs are in descending score order
    last_score = pairs[0][1]
    for pair in pairs[1:]:
        assert pair[1] <= last_score
        last_score = pair[1]

    #  Johanna Quandt <> Frau Johanna Quandt
    jq = (
        Identifier.get("9add84cbb7bb48c7552f8ec7ae54de54eed1e361"),
        Identifier.get("2d3e50433e36ebe16f3d906b684c9d5124c46d76"),
    )
    jq_score = [score for pair, score in pairs if jq == pair][0]

    #  Bayerische Motorenwerke AG <> Bayerische Motorenwerke (BMW) AG
    bmw = (
        Identifier.get("21cc81bf3b960d2847b66c6c862e7aa9b5e4f487"),
        Identifier.get("12570ee94b8dc23bcc080e887539d3742b2a5237"),
    )
    bmw_score = [score for pair, score in pairs if bmw == pair][0]

    # The Quandt pair shares its full name fingerprint; the BMW pair differs
    # by one name part and only connects via individual parts.
    assert jq_score > bmw_score, (jq_score, bmw_score)
    assert jq_score > 100.0, jq_score
    assert 50.0 < bmw_score < 200.0, bmw_score

    # FERRING Arzneimittel GmbH <> Clou Container Leasing GmbH
    false_pos = (
        Identifier.get("f8867c433ba247cfab74096c73f6ff5e36db3ffe"),
        Identifier.get("a061e760dfcf0d5c774fc37c74937193704807b5"),
    )
    false_pos_scores = [score for pair, score in pairs if false_pos == pair]
    if len(false_pos_scores):
        # Dynamic stopwords are based on block size, so weak low-frequency signals
        # can remain in small fixtures. They should not outrank useful name matches.
        assert max(false_pos_scores) < bmw_score, (false_pos_scores, bmw_score)

    assert len(pairs) > 10, len(pairs)


def test_dynamic_stopwords_respect_pair_cost_cap(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"k{i}", "np", "np:kept", 1)
        for i in range(4)
    ] + [
        ("Person", f"s{i}", "np", "np:stopped", 1)
        for i in range(5)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=4,
    )
    try:
        index._build_stopwords()
        stats = {
            token: (df, compatible_pair_cost, stopword)
            for token, df, compatible_pair_cost, stopword in index.con.execute(
                """
                SELECT token, df, compatible_pair_cost, stopword
                FROM token_stats
                ORDER BY token
                """
            ).fetchall()
        }
        assert stats["np:kept"] == (4, 6, False)
        assert stats["np:stopped"] == (5, 10, True)

        index._apply_stopwords("entries", "entries_filtered")
        tokens = {
            token
            for (token,) in index.con.execute(
                "SELECT DISTINCT token FROM entries_filtered"
            ).fetchall()
        }
        assert tokens == {"np:kept"}
    finally:
        index.close()


def test_dynamic_stopwords_count_compatible_schema_pairs_once(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Company", f"c{i}", "np", "np:cross", 1)
        for i in range(2)
    ] + [
        ("LegalEntity", f"l{i}", "np", "np:cross", 1)
        for i in range(3)
    ] + [
        ("Person", f"p{i}", "np", "np:same", 1)
        for i in range(4)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [
            ("Company", "LegalEntity"),
            ("LegalEntity", "Company"),
            ("Person", "Person"),
        ],
        max_bucket_size=4,
    )
    try:
        index._build_stopwords()
        costs = dict(
            index.con.execute(
                """
                SELECT token, compatible_pair_cost
                FROM token_stats
                ORDER BY token
                """
            ).fetchall()
        )
        assert costs["np:cross"] == 6
        assert costs["np:same"] == 6
    finally:
        index.close()


def test_dynamic_stopwords_filter_by_token(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"s{i}", "np", "np:stopped", 1)
        for i in range(5)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=4,
    )
    try:
        index._build_stopwords()
        index.con.execute("""
            CREATE OR REPLACE TABLE matching
                (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
        """)
        index.con.executemany(
            "INSERT INTO matching VALUES (?, ?, ?, ?, ?)",
            [
                ("Person", "m1", "other", "np:stopped", 1),
                ("Person", "m2", "np", "np:kept", 1),
            ],
        )
        index._apply_stopwords("matching", "matching_filtered")
        rows = index.con.execute(
            "SELECT id, field, token FROM matching_filtered ORDER BY id"
        ).fetchall()
        assert rows == [("m2", "np", "np:kept")]
    finally:
        index.close()


def test_pairs_join_filtered_term_frequencies(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"s{i}", "np", "np:stopped", 1)
        for i in range(5)
    ] + [
        ("Person", "k1", "np", "np:kept", 1),
        ("Person", "k2", "np", "np:kept", 1),
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=4,
    )
    try:
        index.con.execute("CREATE OR REPLACE TABLE boosts (field TEXT, boost FLOAT)")
        index._build_frequencies()

        pairs = list(index.pairs())
        assert len(pairs) == 1
        pair, score = pairs[0]
        assert pair == (Identifier.get("k2"), Identifier.get("k1"))
        # each side weighs 1.0 * idf, idf = 1 + ln(7 entities / df 2)
        assert score == pytest.approx(2 * (1 + math.log(7 / 2)))
        assert index.con.execute(
            "SELECT COUNT(*) FROM term_frequencies_all WHERE token = 'np:stopped'"
        ).fetchone() == (5,)
        assert index.con.execute(
            "SELECT COUNT(*) FROM term_frequencies WHERE token = 'np:stopped'"
        ).fetchone() == (0,)
    finally:
        index.close()


def test_matching_keeps_internal_stopword_when_cross_cost_is_safe(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"idx{i}", "np", "np:shared", 1)
        for i in range(5)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=4,
    )
    try:
        index.con.execute("CREATE OR REPLACE TABLE boosts (field TEXT, boost FLOAT)")
        index._build_frequencies()

        assert not index._has_table("stopwords")
        assert not index._has_table("entries_filtered")

        index._ensure_pair_stopwords()
        assert index.con.execute(
            "SELECT COUNT(*) FROM stopwords WHERE token = 'np:shared'"
        ).fetchone() == (1,)
        assert index.con.execute(
            "SELECT COUNT(*) FROM entries_filtered WHERE token = 'np:shared'"
        ).fetchone() == (0,)
        assert index.con.execute(
            "SELECT COUNT(*) FROM term_frequencies_all WHERE token = 'np:shared'"
        ).fetchone() == (5,)
        assert index.con.execute(
            "SELECT COUNT(*) FROM term_frequencies WHERE token = 'np:shared'"
        ).fetchone() == (0,)

        index.con.execute("""
            CREATE OR REPLACE TABLE matching
                (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
        """)
        index.con.execute(
            "INSERT INTO matching VALUES (?, ?, ?, ?, ?)",
            ("Person", "query", "np", "np:shared", 1),
        )

        index._build_matching_stopwords()
        assert index.con.execute(
            """
            SELECT df, compatible_pair_cost, stopword
            FROM matching_token_stats
            WHERE token = 'np:shared'
            """
        ).fetchone() == (1, 5, False)

        index._apply_stopwords(
            "matching",
            "matching_filtered",
            stopwords_table="matching_stopwords",
        )
        assert index.con.execute(
            "SELECT COUNT(*) FROM matching_filtered WHERE token = 'np:shared'"
        ).fetchone() == (1,)

        matches = list(index._find_matches())
        assert len(matches) == 1
        assert matches[0][0] == Identifier.get("query")
        assert {str(match_id) for match_id, _ in matches[0][1]} == {
            f"idx{i}" for i in range(5)
        }
    finally:
        index.close()


def test_matching_stopwords_respect_cross_pair_cost(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"c{i}", "np", "np:cross", 1)
        for i in range(3)
    ] + [
        ("Person", f"k{i}", "np", "np:kept", 1)
        for i in range(2)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=2,
    )
    try:
        index._build_stopwords()
        index.con.execute("""
            CREATE OR REPLACE TABLE term_frequencies_all AS
                SELECT schema, field, token, id, 1.0 AS weight
                FROM entries
        """)
        index.con.execute("""
            CREATE OR REPLACE TABLE matching
                (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
        """)
        index.con.executemany(
            "INSERT INTO matching VALUES (?, ?, ?, ?, ?)",
            [
                ("Person", "mc1", "np", "np:cross", 1),
                ("Person", "mc2", "np", "np:cross", 1),
                ("Person", "mk1", "np", "np:kept", 1),
                ("Person", "mk2", "np", "np:kept", 1),
            ],
        )

        index._build_matching_stopwords()
        stats = {
            token: (df, compatible_pair_cost, stopword)
            for token, df, compatible_pair_cost, stopword in index.con.execute(
                """
                SELECT token, df, compatible_pair_cost, stopword
                FROM matching_token_stats
                ORDER BY token
                """
            ).fetchall()
        }
        assert stats["np:cross"] == (2, 6, True)
        assert stats["np:kept"] == (2, 4, False)

        index._apply_stopwords(
            "matching",
            "matching_filtered",
            stopwords_table="matching_stopwords",
        )
        tokens = {
            token
            for (token,) in index.con.execute(
                "SELECT DISTINCT token FROM matching_filtered"
            ).fetchall()
        }
        assert tokens == {"np:kept"}
    finally:
        index.close()


def test_matching_stopwords_count_oriented_schema_pairs_once(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("LegalEntity", f"l{i}", "np", "np:cross", 1)
        for i in range(3)
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [
            ("Company", "LegalEntity"),
            ("LegalEntity", "Company"),
        ],
        max_bucket_size=3,
    )
    try:
        index._build_stopwords()
        index.con.execute("""
            CREATE OR REPLACE TABLE term_frequencies_all AS
                SELECT schema, field, token, id, 1.0 AS weight
                FROM entries
        """)
        index.con.execute("""
            CREATE OR REPLACE TABLE matching
                (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
        """)
        index.con.executemany(
            "INSERT INTO matching VALUES (?, ?, ?, ?, ?)",
            [
                ("Company", "m1", "np", "np:cross", 1),
                ("Company", "m2", "np", "np:cross", 1),
            ],
        )

        index._build_matching_stopwords()
        stats = dict(
            index.con.execute(
                """
                SELECT token, compatible_pair_cost
                FROM matching_token_stats
                """
            ).fetchall()
        )
        assert stats["np:cross"] == 6
        assert index.con.execute("SELECT COUNT(*) FROM matching_stopwords").fetchone()[
            0
        ] == 0
    finally:
        index.close()


@pytest.mark.parametrize("num_names", [1, 7])
def test_pairs_rank_distinctive_match_above_common_token_noise(
    index_path: Path, test_dataset: Dataset, num_names: int
):
    """Ensure distinctive names outrank common-token noise despite aliases."""
    linker = Linker({})
    store = SimpleMemoryStore(test_dataset, linker)
    writer = store.writer()
    # Vary full-name fingerprints and name parts to exercise both token classes.
    names = [
        "Journal Atlas Publishing House",
        "Journal Atlas Publishing House Ltd",
        "Zhurnal Atlas Pablishing Khaus",
        "Журнал Атлас Паблишинг Хаус",
        "Izdatelstvo Atlas",
        "Издательство Атлас",
        "Atlas Journal Verlag",
    ][:num_names]
    writer.add_entity(
        StatementEntity.from_data(
            test_dataset,
            {
                "id": "journal-atlas",
                "schema": "Company",
                "properties": {"name": names},
            },
        )
    )
    writer.add_entity(
        StatementEntity.from_data(
            test_dataset,
            {
                "id": "fsf-atlas",
                "schema": "Company",
                "properties": {"name": ["Journal Atlas Publishing House"]},
            },
        )
    )
    for i in range(50):
        writer.add_entity(
            StatementEntity.from_data(
                test_dataset,
                {
                    "id": f"decoy-{i}",
                    "schema": "Person",
                    "properties": {"name": ["Ahmad"], "country": ["iq"]},
                },
            )
        )
    writer.flush()

    index = Index(store.default_view(), index_path)
    try:
        index.build()
        pairs = list(index.pairs(max_pairs=2000))
        # vacuity guard: the decoy pairs must actually be present -- above the
        # stopword crossover they vanish and rank 0 would win by default
        assert len(pairs) == 50 * 49 // 2 + 1, len(pairs)
        genuine = (Identifier.get("journal-atlas"), Identifier.get("fsf-atlas"))
        assert pairs[0][0] in (genuine, tuple(reversed(genuine))), pairs[0]
        # a strict win, not a tie broken by luck
        assert pairs[0][1] > pairs[1][1], (pairs[0], pairs[1])
    finally:
        index.close()


def test_index_xref(test_dataset: Dataset, dstore: SimpleMemoryStore, dindex: Index):
    assert not dindex._has_table("stopwords")
    linker = Linker({})
    ostore = SimpleMemoryStore(test_dataset, linker)
    a = StatementEntity.from_data(
        test_dataset,
        {
            "id": "a",
            "schema": "Company",
            "properties": {
                "name": ["Bayerische Motorenwerke AG"],
                "address": ["Moscow"],
            },
        },
    )
    b = StatementEntity.from_data(
        test_dataset,
        {
            "id": "b",
            "schema": "Company",
            "properties": {
                "name": ["Volkswagen AG"],
                "address": ["Moscow"],
            },
        },
    )
    c = StatementEntity.from_data(
        test_dataset,
        {
            "id": "c",
            "schema": "Company",
            "properties": {
                "name": ["Bayerische Motorenwerke AG (BMW) AG"],
                "address": ["Moscow"],
            },
        },
    )
    writer = ostore.writer()
    writer.add_entity(a)
    writer.add_entity(b)
    writer.add_entity(c)
    writer.flush()

    matches = {
        str(ident): matches
        for ident, matches in dindex.match_entities(ostore.default_view().entities())
    }
    assert not dindex._has_table("stopwords")
    assert {"a", "c"}.issubset(matches), matches

    view = dstore.default_view()
    a_top = matches["a"][0]
    a_top_entity = view.get_entity(str(a_top[0]))
    assert a_top_entity is not None
    assert a_top_entity.caption == "Bayerische Motorenwerke AG"

    c_top = matches["c"][0]
    c_top_entity = view.get_entity(str(c_top[0]))
    assert c_top_entity is not None
    assert c_top_entity.caption == "Bayerische Motorenwerke (BMW) AG"

    if "b" in matches:
        assert matches["b"][0][1] < a_top[1], matches["b"]


# Candidate ladder: entity e{i} shares i+1 distinct np tokens with subject q,
# so scores strictly increase with i (same token weight, log token credit).
LADDER_ENTRIES = [
    ("Person", f"e{i}", "np", f"np:t{i}_{j}", 1)
    for i in range(5)
    for j in range(i + 1)
]
LADDER_MATCHING = [
    ("Person", "q", "np", f"np:t{i}_{j}", 1) for i in range(5) for j in range(i + 1)
]


def test_matching_truncates_to_max_candidates_in_query(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = make_manual_index(
        index_path,
        dstore,
        LADDER_ENTRIES,
        [("Person", "Person")],
        max_bucket_size=10,
        options={"max_candidates": 3},
    )
    try:
        matches = run_matching(index, LADDER_MATCHING)
        assert [mid for mid, _ in matches["q"]] == ["e4", "e3", "e2"]
        scores = [score for _, score in matches["q"]]
        assert scores == sorted(scores, reverse=True)
    finally:
        index.close()


def test_matching_keeps_all_candidates_at_exact_max_candidates(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = make_manual_index(
        index_path,
        dstore,
        LADDER_ENTRIES,
        [("Person", "Person")],
        max_bucket_size=10,
        options={"max_candidates": 5},
    )
    try:
        matches = run_matching(index, LADDER_MATCHING)
        assert [mid for mid, _ in matches["q"]] == ["e4", "e3", "e2", "e1", "e0"]
    finally:
        index.close()


# Three candidates with boost-separated scores: eA (name, boost 15) is the
# best, eC (np, boost 5) sits at 1/3 of it, eB (word, boost 0.5) at 1/30 —
# below the default 0.1 relative score floor.
FLOOR_BOOSTS = {"name": 15.0, "np": 5.0, "word": 0.5}
FLOOR_ENTRIES = [
    ("Person", "eA", "name", "fp:acmeholdings", 1),
    ("Person", "eC", "np", "np:acme", 1),
    ("Person", "eB", "word", "w:junk", 1),
]
FLOOR_MATCHING = [
    ("Person", "q", "name", "fp:acmeholdings", 1),
    ("Person", "q", "np", "np:acme", 1),
    ("Person", "q", "word", "w:junk", 1),
]


def test_matching_applies_relative_score_floor(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = make_manual_index(
        index_path,
        dstore,
        FLOOR_ENTRIES,
        [("Person", "Person")],
        max_bucket_size=10,
    )
    try:
        matches = run_matching(index, FLOOR_MATCHING, boosts=FLOOR_BOOSTS)
        assert [mid for mid, _ in matches["q"]] == ["eA", "eC"]
    finally:
        index.close()


def test_matching_score_floor_disabled_at_zero(
    index_path: Path, dstore: SimpleMemoryStore
):
    index = make_manual_index(
        index_path,
        dstore,
        FLOOR_ENTRIES,
        [("Person", "Person")],
        max_bucket_size=10,
        options={"min_score_ratio": 0.0},
    )
    try:
        matches = run_matching(index, FLOOR_MATCHING, boosts=FLOOR_BOOSTS)
        assert [mid for mid, _ in matches["q"]] == ["eA", "eC", "eB"]
    finally:
        index.close()


def test_matching_score_floor_is_per_subject(
    index_path: Path, dstore: SimpleMemoryStore
):
    """A weak-evidence subject keeps its best candidate even when another
    subject in the batch has a much stronger best (the floor must not leak
    across window partitions)."""
    entries = FLOOR_ENTRIES + [("Person", "eD", "word", "w:other", 1)]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=10,
    )
    try:
        matching = FLOOR_MATCHING + [("Person", "q2", "word", "w:other", 1)]
        matches = run_matching(index, matching, boosts=FLOOR_BOOSTS)
        assert [mid for mid, _ in matches["q"]] == ["eA", "eC"]
        assert [mid for mid, _ in matches["q2"]] == ["eD"]
    finally:
        index.close()


def test_matching_excludes_subject_from_own_candidates(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", "e1", "np", "np:tok", 1),
        ("Person", "e2", "np", "np:tok", 1),
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=10,
    )
    try:
        matches = run_matching(index, [("Person", "e1", "np", "np:tok", 1)])
        assert [mid for mid, _ in matches["e1"]] == ["e2"]
    finally:
        index.close()


def test_matching_orders_equal_scores_by_candidate_id(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", cid, "np", "np:shared", 1) for cid in ("idxc", "idxa", "idxb")
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=10,
    )
    try:
        matches = run_matching(index, [("Person", "q", "np", "np:shared", 1)])
        assert [mid for mid, _ in matches["q"]] == ["idxa", "idxb", "idxc"]
    finally:
        index.close()


def test_matching_yields_all_subjects_with_candidates(
    index_path: Path, dstore: SimpleMemoryStore
):
    entries = [
        ("Person", f"{prefix}{i}", "np", f"np:t{i}", 1)
        for i in range(7)
        for prefix in ("a", "b")
    ]
    index = make_manual_index(
        index_path,
        dstore,
        entries,
        [("Person", "Person")],
        max_bucket_size=10,
    )
    try:
        matching = [("Person", f"q{i}", "np", f"np:t{i}", 1) for i in range(7)]
        matches = run_matching(index, matching)
        assert len(matches) == 7
        for i in range(7):
            assert [mid for mid, _ in matches[f"q{i}"]] == [f"a{i}", f"b{i}"]
    finally:
        index.close()
