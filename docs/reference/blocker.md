# Blocking index

The blocking index finds candidate duplicate pairs by shared tokens, so that only a small fraction of all possible entity pairs needs to be scored.

Comparing every entity against every other entity is quadratic: a dataset of one million entities has half a trillion pairs. Blocking cuts this down by tokenizing each entity — into name parts, phonetic forms, identifiers, and words — and only pairing entities that share at least one token. Each candidate pair gets a rough similarity score based on term frequency and per-field boost factors. That score ranks candidates for the more expensive [matching](matching.md) stage; it is not itself a match decision.

The index is backed by [DuckDB](https://duckdb.org/). It keeps data in memory and spills to disk as it approaches the configured memory limit. Two environment variables control resource use:

- `NOMENKLATURA_DUCKDB_MEMORY` — memory limit for the DuckDB buffer manager (e.g. `4GB`). DuckDB uses more memory than this setting in total, so leave headroom.
- `NOMENKLATURA_DUCKDB_THREADS` — number of threads DuckDB may use.

The `nk xref` command builds a blocking index under its data path (`nomenklatura.data/xref-index` by default) and feeds the resulting candidate pairs to a scoring algorithm. See the [deduplication tutorial](../tutorial.md) for the full workflow.

## Interface

::: nomenklatura.blocker.Index
