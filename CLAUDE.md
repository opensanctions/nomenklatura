# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
make test
# or directly:
pytest --cov-report html --cov-report term --cov=nomenklatura tests/

# Run a single test
pytest tests/test_resolver.py::test_function_name -v

# Type checking
make typecheck
# or:
mypy --strict nomenklatura/

# Run both tests and type check
make check
```

## Architecture

Nomenklatura is a data deduplication and entity integration framework for [Follow the Money (FtM)](https://followthemoney.tech/) entities. The core workflow: ingest FtM entities → block candidates → score pairs → record judgements → export merged entities.

### Key abstractions

**`Resolver`** (`nomenklatura/resolver/resolver.py`) — The central graph structure. Stores edges (`Edge`) representing `Judgement`s (POSITIVE/NEGATIVE/UNSURE/NO_JUDGEMENT) between entity ID pairs. Implements connected-components to find canonical IDs and evaluate transitive judgements. Backed by SQLAlchemy (defaults to SQLite at `nomenklatura.db`; configurable via `NOMENKLATURA_DB_URL`). The `Resolver` extends `Linker`, which is the read-only view used throughout the rest of the codebase.

**`Store`** (`nomenklatura/store/base.py`) — Generic triple store for FtM statement-based entities. Implementations:
- `MemoryStore` — in-memory, used for CLI file-based workflows
- `SQLStore` — PostgreSQL/SQLite persistence
- `LevelStore` / `RedisStore` — alternative KV backends (optional deps)

**`blocker.Index`** (`nomenklatura/blocker/index.py`) — DuckDB-backed inverted index for blocking (finding candidate pairs). Tokenizes entities into name parts, phonetics, symbols, and words. Used by `xref`.

**Matching algorithms** (`nomenklatura/matching/`) — Scoring algorithms implement `ScoringAlgorithm` from `matching/types.py`. Available algorithms registered in `matching/__init__.py`:
- `RegressionV1` — default; sklearn logistic regression trained on FtM feature comparisons
- `EntityResolveRegression` — entity resolution regression model
- `LogicV1`, `LogicV2` — rule-based logic matchers
- `NameMatcher`, `NameQualifiedMatcher` — name-only matchers

Feature comparisons are in `matching/compare/` (names, dates, countries, identifiers, addresses, gender). These return normalized floats fed to the regression models.

**Enrichment** (`nomenklatura/enrich/`) — Framework for linking entities to external data sources. `BaseEnricher` is the ABC; implementations include `AlephEnricher`, `YenteEnricher`, `OpenCorporatesEnricher`, `WikidataEnricher`, etc. Enrichers are configured via YAML and use a SQLite-backed `Cache`.

**TUI** (`nomenklatura/tui/`) — Textual-based terminal UI for interactive deduplication (`dedupe` CLI command).

**`xref`** (`nomenklatura/xref.py`) — Orchestrates the cross-reference pipeline: builds a blocking index, scores candidate pairs, and saves unsure judgements to the resolver.

### CLI entry points

Both `nk` and `nomenklatura` invoke `nomenklatura.cli:cli`. Key commands:
- `xref` — generate dedupe candidates using blocking index
- `dedupe` — interactive TUI for judging candidates
- `apply` — apply resolver to entity stream (merge duplicates)
- `match` / `enrich` — enrichment pipeline commands
- `load-resolver` / `dump-resolver` — import/export resolver decisions

### Settings (`nomenklatura/settings.py`)

Environment variables: `NOMENKLATURA_DB_URL`, `NOMENKLATURA_DB_POOL_SIZE`, `NOMENKLATURA_REDIS_URL`, `NOMENKLATURA_STATEMENT_TABLE`, `NOMENKLATURA_DUCKDB_MEMORY`, `NOMENKLATURA_DUCKDB_THREADS`, `NOMENKLATURA_LEVELDB_MAX_FILES`.

### Public API

```python
from nomenklatura import Resolver, Store, View, Judgement, Linker
```
