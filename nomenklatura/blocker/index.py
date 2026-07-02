# Test realistic memory usage with constrained memory because duckdb only spills
# when it's constrained, but you don't know how much more memory it will use than
# the memory limit.
# e.g. docker build . --tag opensanctions and
# docker run -ti --name xref \
#            -v ./data:/data
#            -v .:/opensanctions \
#            --memory 3G
#            -e ZAVOD_DATA_PATH=/data
#            -e ZAVOD_DATABASE_URI=postgresql://postgres:password@host.docker.internal:5432/dev
#            opensanctions bash
#
# Debugging memory usage?
# https://duckdb.org/docs/stable/guides/troubleshooting/oom_errors
#
# Most DuckDB operations spill to disk when its memory_limit setting is reached.
#
# DuckDB uses more memory than its memory_limit setting.
# > This limit only applies to the buffer manager.
# https://duckdb.org/docs/1.2/operations_manual/limits
#
# Beyond that, other things in zavod also use memory.
#
# When duckdb's memory_limit is reached and it cannot spill to disk,
# it will throw an error like duckdb.duckdb.OutOfMemoryException:
# Out of Memory Error: could not allocate block of size 30.5 MiB (32.8 MiB/47.6 MiB used)
#
# When the process is killed due to the operating system running out of memory,
# making memory_limit smaller might help fit what the buffer manager manages,
# plus all the additional DuckDB and non-DuckDB memory usage.
import csv
import duckdb
import logging
from pathlib import Path
from itertools import islice
from rigour.reset import reset_caches
from collections import defaultdict
from typing import Any, Dict, Generator, Iterable, List, Tuple, TypeVar

from followthemoney import DS, SE, StatementEntity, model, registry
from nomenklatura.settings import DUCKDB_MEMORY, DUCKDB_THREADS
from nomenklatura.resolver import Identifier
from nomenklatura.store import View
from nomenklatura.blocker.tokenizer import (
    NAME_PART_FIELD,
    WORD_FIELD,
    tokenize_entity,
)

DuckDBConfig = Dict[str, str | bool | int | float | list[str]]
BlockingMatches = List[Tuple[Identifier, float]]
R = TypeVar("R")

log = logging.getLogger(__name__)

BATCH_SIZE = 10_000


def batched(iterable: Iterable[R], n: int) -> Generator[Tuple[R, ...], None, None]:
    iterator = iter(iterable)
    while batch := tuple(islice(iterator, n)):
        yield batch


class Index(object):
    """
    An index using DuckDB for token matching and scoring, keeping data in memory
    until it needs to spill to disk as it approaches the configured memory limit.

    Pairs match if they share one or more tokens. A basic similarity score is calculated
    cumulatively based on each token's Term Frequency (TF) and the field's boost factor.
    """

    BOOSTS = {
        NAME_PART_FIELD: 5.0,
        WORD_FIELD: 0.5,
        registry.name.name: 15.0,
        registry.phone.name: 10.0,
        registry.email.name: 10.0,
        registry.address.name: 1.0,
        registry.identifier.name: 10.0,
    }

    def __init__(
        self,
        view: View[DS, SE],
        data_dir: Path,
        options: Dict[str, Any] = {},
    ):
        self.view = view
        self.max_candidates = int(options.get("max_candidates", 75))
        self.max_token_pair_cost = int(options.get("max_token_pair_cost", 2000))
        if self.max_token_pair_cost < 0:
            raise ValueError("max_token_pair_cost must be >= 0")
        self.match_batch: int = int(options.get("match_batch", 1_000))
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.duckdb_config: DuckDBConfig = {
            "preserve_insertion_order": False,
            "python_enable_replacements": False,
        }

        # https://duckdb.org/docs/guides/performance/environment
        # > For ideal performance,
        # > aggregation-heavy workloads require approx. 5 GB memory per thread and
        # > join-heavy workloads require approximately 10 GB memory per thread.
        # > Aim for 5-10 GB memory per thread.
        memory_budget = options.get("memory", DUCKDB_MEMORY)
        """Memory budget in megabytes"""
        if memory_budget is not None:
            self.duckdb_config["memory_limit"] = f"{memory_budget}MB"

        if DUCKDB_THREADS is not None:
            # > If you have a limited amount of memory, try to limit the number of threads
            self.duckdb_config["threads"] = int(DUCKDB_THREADS)

        log.info("DuckDB index configured: %r", self.duckdb_config)
        self.duckdb_path = self.data_dir / "index.duckdb"
        self.con = duckdb.connect(self.duckdb_path, config=self.duckdb_config)

    def load_entities(self, table: str, entities: Iterable[StatementEntity]) -> None:
        path = self.data_dir / f"{table}.csv"
        self.con.execute(f"""
        CREATE OR REPLACE TABLE {table}
            (schema TEXT, id TEXT, field TEXT, token TEXT, count INT)
        """)
        self.con.execute(f"DELETE FROM {table}")

        def generate() -> Generator[Tuple[str, str, str, str, int], None, None]:
            idx = 0
            tokens = 0
            for entity in entities:
                if not entity.schema.matchable or entity.id is None:
                    continue
                counts: Dict[Tuple[str, str], int] = defaultdict(int)
                for field, token in tokenize_entity(entity):
                    token = token[:40]  # Limit token length
                    counts[(field, token)] += 1

                for (field, token), count in counts.items():
                    yield (entity.schema.name, entity.id, field, token, count)
                    tokens += 1

                idx += 1
                if idx % 50000 == 0:
                    log.info("Loaded %d entities (%d tokens)", idx, tokens)

        log.info("Loading data to table %r...", table)
        for batch in batched(generate(), 500_000):
            with open(path, "w", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                for row in batch:
                    writer.writerow(row)
            self.con.execute(f"""
                INSERT INTO {table} SELECT * FROM
                    read_csv('{path.as_posix()}',
                        HEADER=FALSE,
                        QUOTE='\"',
                        DELIM=',',
                        ENCODING='utf-8',
                        COMPRESSION='none',
                        SAMPLE_SIZE=5
                    )
            """)

        path.unlink(missing_ok=True)
        reset_caches()
        self.con.execute("CHECKPOINT")

    def entity_count(self, table: str) -> int:
        # check the table exists:
        tables_ = self.con.execute("PRAGMA show_tables").fetchall()
        tables = {t[0] for t in tables_}
        if table not in tables:
            return 0
        q = f"SELECT COUNT(DISTINCT id) FROM {table}"
        res = self.con.execute(q).fetchone()
        return res[0] if res is not None else 0

    def build(self) -> None:
        """Index all entities in the dataset."""
        log.info("Building index from: %r...", self.view)
        self.con.execute("CREATE OR REPLACE TABLE boosts (field TEXT, boost FLOAT)")
        for field, boost in self.BOOSTS.items():
            self.con.execute("INSERT INTO boosts VALUES (?, ?)", [field, boost])
        for type in registry.types:
            if type.name in self.BOOSTS:
                continue
            self.con.execute("INSERT INTO boosts VALUES (?, ?)", [type.name, 1.0])

        q = """CREATE OR REPLACE TABLE schemata ("left" TEXT, "right" TEXT)"""
        self.con.execute(q)
        for left in model.schemata.values():
            for right in left.matchable_schemata:
                q = "INSERT INTO schemata VALUES (?, ?)"
                self.con.execute(q, [left.name, right.name])

        schemata = list(model.matchable_schemata())
        self.load_entities("entries", self.view.entities(include_schemata=schemata))
        self._build_frequencies()
        log.info("Index built.")

    def _build_stopwords(self) -> None:
        log.info(
            "Building dynamic stopwords with max token pair cost %d...",
            self.max_token_pair_cost,
        )
        token_schema_counts_query = """
        CREATE OR REPLACE TABLE token_schema_counts AS
            SELECT
                token,
                any_value(field) AS field,
                schema,
                count(*) AS df,
                sum("count") AS freq
            FROM entries
            GROUP BY token, schema
        """
        self.con.execute(token_schema_counts_query)

        token_stats_query = """
        CREATE OR REPLACE TABLE token_stats AS
            WITH schema_pairs AS (
                SELECT DISTINCT
                    least("left", "right") AS left_schema,
                    greatest("left", "right") AS right_schema
                FROM schemata
            ),
            compatible AS (
                SELECT
                    l.token,
                    sum(
                        CASE
                            WHEN l.schema = r.schema THEN
                                cast(l.df * (l.df - 1) / 2 AS HUGEINT)
                            ELSE
                                cast(l.df * r.df AS HUGEINT)
                        END
                    ) AS compatible_pair_cost
                FROM token_schema_counts AS l
                JOIN token_schema_counts AS r
                    ON l.token = r.token
                   AND l.schema <= r.schema
                JOIN schema_pairs AS s
                    ON s.left_schema = l.schema
                   AND s.right_schema = r.schema
                GROUP BY l.token
            ),
            totals AS (
                SELECT
                    token,
                    any_value(field) AS field,
                    sum(freq) AS freq,
                    sum(df) AS df
                FROM token_schema_counts
                GROUP BY token
            )
            SELECT
                totals.token,
                totals.field,
                totals.freq,
                totals.df,
                ifnull(compatible.compatible_pair_cost, 0) AS compatible_pair_cost,
                ifnull(compatible.compatible_pair_cost, 0) > ? AS stopword
            FROM totals
            LEFT JOIN compatible ON compatible.token = totals.token
        """
        self.con.execute(token_stats_query, [self.max_token_pair_cost])

        stopwords_query = """
        CREATE OR REPLACE TABLE stopwords AS
            SELECT token, field, freq, df, compatible_pair_cost
            FROM token_stats
            WHERE stopword
        """
        self.con.execute(stopwords_query)
        self._log_stopword_stats("token_stats", "stopwords", "Dynamic stopwords")

    def _build_matching_stopwords(self) -> None:
        log.info(
            "Building matching stopwords with max token pair cost %d...",
            self.max_token_pair_cost,
        )
        matching_token_schema_counts_query = """
        CREATE OR REPLACE TABLE matching_token_schema_counts AS
            SELECT
                token,
                any_value(field) AS field,
                schema,
                count(*) AS df,
                sum("count") AS freq
            FROM matching
            GROUP BY token, schema
        """
        self.con.execute(matching_token_schema_counts_query)

        matching_token_stats_query = """
        CREATE OR REPLACE TABLE matching_token_stats AS
            WITH indexed_token_schema_counts AS (
                SELECT
                    token,
                    schema,
                    count(*) AS df
                FROM term_frequencies_all
                GROUP BY token, schema
            ),
            compatible AS (
                SELECT
                    m.token,
                    sum(cast(m.df * i.df AS HUGEINT)) AS compatible_pair_cost
                FROM matching_token_schema_counts AS m
                JOIN indexed_token_schema_counts AS i
                    ON i.token = m.token
                JOIN schemata AS s
                    ON s.left = m.schema
                   AND s.right = i.schema
                GROUP BY m.token
            ),
            totals AS (
                SELECT
                    token,
                    any_value(field) AS field,
                    sum(freq) AS freq,
                    sum(df) AS df
                FROM matching_token_schema_counts
                GROUP BY token
            )
            SELECT
                totals.token,
                totals.field,
                totals.freq,
                totals.df,
                ifnull(compatible.compatible_pair_cost, 0) AS compatible_pair_cost,
                ifnull(compatible.compatible_pair_cost, 0) > ? AS stopword
            FROM totals
            LEFT JOIN compatible ON compatible.token = totals.token
        """
        self.con.execute(matching_token_stats_query, [self.max_token_pair_cost])

        matching_stopwords_query = """
        CREATE OR REPLACE TABLE matching_stopwords AS
            SELECT token, field, freq, df, compatible_pair_cost
            FROM matching_token_stats
            WHERE stopword
        """
        self.con.execute(matching_stopwords_query)
        self._log_stopword_stats(
            "matching_token_stats",
            "matching_stopwords",
            "Matching stopwords",
        )

    def _log_stopword_stats(
        self, stats_table: str, stopwords_table: str, label: str
    ) -> None:
        stats_query = f"""
            SELECT
                count(*) AS tokens,
                ifnull(sum(CASE WHEN stopword THEN 1 ELSE 0 END), 0) AS stopwords,
                ifnull(sum(CASE WHEN stopword THEN compatible_pair_cost ELSE 0 END), 0)
                    AS stopped_pair_cost,
                ifnull(sum(CASE WHEN NOT stopword THEN compatible_pair_cost ELSE 0 END), 0)
                    AS kept_pair_cost,
                ifnull(max(CASE WHEN NOT stopword THEN compatible_pair_cost ELSE NULL END), 0)
                    AS max_kept_pair_cost,
                ifnull(max(CASE WHEN NOT stopword THEN df ELSE NULL END), 0) AS max_kept_df
            FROM {stats_table}
        """
        stats = self.con.execute(stats_query).fetchone()
        if stats is None:
            return
        (
            tokens,
            stopwords,
            stopped_pair_cost,
            kept_pair_cost,
            max_kept_pair_cost,
            max_kept_df,
        ) = stats
        log.info(
            "%s built: %d/%d tokens stopped, "
            "compatible pair cost kept=%d stopped=%d, "
            "max kept token cost=%d, max kept df=%d",
            label,
            stopwords,
            tokens,
            kept_pair_cost,
            stopped_pair_cost,
            max_kept_pair_cost,
            max_kept_df,
        )
        top_stopwords_query = f"""
            SELECT field, token, df, compatible_pair_cost
            FROM {stopwords_table}
            ORDER BY compatible_pair_cost DESC, token ASC
            LIMIT 10
        """
        top_stopwords = "\n".join(
            f"{field} {token} df={df} cost={compatible_pair_cost}"
            for field, token, df, compatible_pair_cost in self.con.execute(
                top_stopwords_query
            ).fetchall()
        )
        if len(top_stopwords):
            log.info("Top %s:\n%s\n", label.lower(), top_stopwords)

    def _apply_stopwords(
        self,
        origin_table: str,
        target_table: str,
        stopwords_table: str | None = "stopwords",
    ) -> None:
        log.info("Filtering stopwords from %r, as %r...", origin_table, target_table)
        if stopwords_table is None:
            q = f"""
            CREATE OR REPLACE TABLE {target_table} as
                SELECT e.*
                FROM {origin_table} AS e
            """
        else:
            q = f"""
            CREATE OR REPLACE TABLE {target_table} as
                SELECT e.*
                FROM {origin_table} AS e
                LEFT OUTER JOIN {stopwords_table} AS sw ON sw.token = e.token
                WHERE sw.token is NULL
            """
        self.con.execute(q)

    def _build_frequencies(self) -> None:
        self._build_stopwords()
        self._apply_stopwords("entries", "entries_filtered")
        log.info("Calculating term frequencies...")
        term_frequencies_query = """
        CREATE OR REPLACE TABLE term_frequencies_all AS
            WITH field_len AS (
                SELECT e.field, e.id, sum(e.count) as len
                    FROM entries e
                    GROUP BY e.field, e.id
            )
            SELECT e.schema, e.field, e.token, e.id, (e.count/f.len) * ifnull(boo.boost, 1) as tf
            FROM entries AS e
            JOIN field_len AS f ON f.field = e.field AND f.id = e.id
            LEFT OUTER JOIN boosts boo ON f.field = boo.field
        """
        self.con.execute(term_frequencies_query)
        self.con.execute("""
            CREATE OR REPLACE TABLE term_frequencies AS
                SELECT *
                FROM term_frequencies_all
        """)

    def pairs(
        self, max_pairs: int = 10_000
    ) -> Iterable[Tuple[Tuple[Identifier, Identifier], float]]:
        log.info("Generating pairs...")
        pairs_query = """
            SELECT "left".id, "right".id, sum(("left".tf + "right".tf)) as score
            FROM term_frequencies_all as "left"
            JOIN term_frequencies_all as "right" ON "left".token = "right".token
            INNER JOIN schemata ON schemata.left = "left".schema AND schemata.right = "right".schema
            LEFT OUTER JOIN stopwords AS sw ON sw.token = "left".token
            WHERE "left".id > "right".id
              AND sw.token is NULL
            GROUP BY "left".id, "right".id
            ORDER BY score DESC
            LIMIT ?
        """
        results = self.con.execute(pairs_query, [max_pairs])
        while batch := results.fetchmany(BATCH_SIZE):
            for left, right, score in batch:
                yield (Identifier.get(left), Identifier.get(right)), score

    def match_entities(
        self, entities: Iterable[StatementEntity]
    ) -> Generator[
        Tuple[Identifier, BlockingMatches],
        None,
        None,
    ]:
        self.load_entities("matching", entities)
        self._build_matching_stopwords()
        self._apply_stopwords(
            "matching",
            "matching_filtered",
            stopwords_table="matching_stopwords",
        )
        yield from self._find_matches()

    def _find_matches(
        self,
    ) -> Generator[
        Tuple[Identifier, BlockingMatches],
        None,
        None,
    ]:
        q = "SELECT COUNT(DISTINCT id) FROM matching_filtered"
        res = self.con.execute(q).fetchone()
        num_matching = res[0] if res is not None else 0
        chunks = max(1, num_matching // self.match_batch)

        chunk_table_query = """
        CREATE OR REPLACE TABLE matching_chunks AS
            WITH ids AS (SELECT DISTINCT id FROM matching_filtered)
            SELECT id, ntile(?) OVER (ORDER BY id) as chunk FROM ids
        """
        self.con.execute(chunk_table_query, [chunks])

        log.info("Matching %d entities in %d chunks...", num_matching, chunks)
        for chunk in range(1, chunks + 1):
            chunk_query = """
            SELECT m.id AS matching_id, tf.id AS matches_id, SUM(tf.tf) AS score
                FROM matching_chunks c
                JOIN matching_filtered m ON c.id = m.id
                JOIN term_frequencies_all tf
                ON m.token = tf.token
                INNER JOIN schemata s
                ON s.left = m.schema AND s.right = tf.schema
                WHERE c.chunk = ?
                GROUP BY m.id, tf.id
                ORDER BY m.id, score DESC
            """
            results = self.con.execute(chunk_query, [chunk])
            previous_id = None
            matches: BlockingMatches = []
            while batch := results.fetchmany(BATCH_SIZE):
                for matching_id, match_id, score in batch:
                    # first row
                    if previous_id is None:
                        previous_id = matching_id
                    # Next pair of subject and candidates
                    if matching_id != previous_id:
                        if matches:
                            yield Identifier.get(previous_id), matches
                        matches = []
                        previous_id = matching_id
                    if len(matches) <= self.max_candidates:
                        matches.append((Identifier.get(match_id), score))
            # Last pair or subject and candidates
            if matches and previous_id is not None:
                yield Identifier.get(previous_id), matches[: self.max_candidates]
                # yield Identifier.get(previous_id), matches

    def close(self) -> None:
        self.con.close()

    def __repr__(self) -> str:
        return "<DuckDBIndex(%r, %r)>" % (
            self.view.scope.name,
            self.con,
        )
