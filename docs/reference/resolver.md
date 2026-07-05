# Resolver

The resolver records judgements about whether pairs of entities are the same, and derives a canonical identifier for each cluster of merged entities.

Deduplication in `nomenklatura` is non-destructive: instead of rewriting entity records, every decision — "these two are the same", "these are different", "not sure yet" — is stored as an edge between two entity IDs. The [Judgement][nomenklatura.judgement.Judgement] on each edge can be `POSITIVE`, `NEGATIVE`, or `UNSURE`; candidate pairs produced by `nk xref` are stored as `NO_JUDGEMENT` edges until a human decides them. Positive judgements are transitive: if A is B and B is C, then A, B, and C form one cluster, and the resolver assigns the whole cluster one **canonical ID**. Source data stays untouched, and any decision can be revisited later.

The [Resolver][nomenklatura.resolver.Resolver] is backed by a SQL database via SQLAlchemy — by default a SQLite file named `nomenklatura.db` in the working directory. Set `NOMENKLATURA_DB_URL` to use a different database, e.g. PostgreSQL for a shared, long-running installation.

The [Linker][nomenklatura.resolver.Linker] is the read-only view of the same information: a plain mapping from entity IDs to canonical IDs, holding only the positive merges. Loading a `Linker` (via `Resolver.get_linker()`) takes much less memory than the full resolver, so prefer it when applying decisions in bulk — for example when streaming statements through `nk apply-statements`.

To decide entity pairs programmatically rather than through the `nk dedupe` interface:

```python
from nomenklatura import Resolver, Judgement
from nomenklatura.db import make_session

with make_session() as session:
    resolver = Resolver(session, create=True)
    resolver.load_into_memory()
    canonical = resolver.decide(
        "source-a-entity-17",
        "source-b-entity-233",
        Judgement.POSITIVE,
    )
# Exiting the session block commits the decision to the database.
```

## Interface

::: nomenklatura.resolver.Resolver

::: nomenklatura.resolver.Linker

::: nomenklatura.judgement.Judgement

::: nomenklatura.resolver.Identifier

::: nomenklatura.resolver.Edge
