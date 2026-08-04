# Blocking index

The blocking index finds candidate duplicate pairs by shared tokens, so that only a small fraction of all possible entity pairs needs to be scored.

Comparing every entity against every other entity is quadratic: a dataset of one million entities has half a trillion pairs. Blocking cuts this down by tokenizing each entity — into name parts, phonetic forms, identifiers, and words — and only pairing entities that share at least one token. Each candidate pair gets a rough similarity score that weighs shared tokens by their rarity across the index and per-field boost factors. That score ranks candidates for the more expensive [matching](matching.md) stage; it is not itself a match decision.

The index is backed by [DuckDB](https://duckdb.org/). It keeps data in memory and spills to disk as it approaches the configured memory limit. Two environment variables control resource use:

- `NOMENKLATURA_DUCKDB_MEMORY` — memory limit in megabytes for the DuckDB buffer manager (e.g. `4000`). DuckDB uses more memory than this setting in total, so leave headroom.
- `NOMENKLATURA_DUCKDB_THREADS` — number of threads DuckDB may use.

When matching a batch of entities against the index (enrichment), each subject's candidate list is truncated inside the query: at most `max_candidates` candidates (default 75), and only candidates scoring at least `min_score_ratio` (default 0.1) of that subject's best candidate score. Set `min_score_ratio: 0` to disable the relative floor. By default the whole batch is matched in one query; setting `match_batch` to a positive number splits it into chunks of roughly that many subjects, trading throughput for a lower peak resource footprint on constrained hosts.

The `nk xref` command builds a blocking index under its data path (`nomenklatura.data/xref-index` by default) and feeds the resulting candidate pairs to a scoring algorithm. See the [deduplication tutorial](../tutorial.md) for the full workflow.

## Interface

::: nomenklatura.blocker.Index
