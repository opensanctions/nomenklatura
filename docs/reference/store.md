# Stores

A store reads and writes [statement-based](https://followthemoney.tech/docs/statements/) FollowTheMoney (FtM) entities, and assembles them into their merged, canonical form on retrieval.

Stores are where deduplication decisions meet the data. When an entity is read from a store, its statements are grouped by canonical ID — as defined by a [Linker](resolver.md) — so a cluster of merged source records comes back as one entity. The source statements themselves are never rewritten; changing a judgement in the resolver changes what the store returns, not what it contains.

Three classes cooperate:

- **`Store`** — the storage backend, bound to a dataset scope and a linker.
- **`Writer`** — bulk write operations: add entities or individual statements, remove them by entity ID.
- **`View`** — read access over a dataset scope: get an entity by ID, iterate all entities, or traverse inverted relationships (which entities reference this one?).

## Choosing a backend

Use [MemoryStore][nomenklatura.store.MemoryStore] for datasets that fit in memory — this is what the `nk` command line uses when it reads entities from a file, via [load_entity_file_store][nomenklatura.store.load_entity_file_store]. Use [SQLStore][nomenklatura.store.sql.SQLStore] to persist statements to SQLite or PostgreSQL. Two further backends, `LevelStore` (LevelDB) and `RedisStore`, live in `nomenklatura.store.level` and `nomenklatura.store.redis_` and require the optional `plyvel` and `redis` dependencies.

```python
from pathlib import Path
from nomenklatura import Resolver
from nomenklatura.db import make_session
from nomenklatura.store import load_entity_file_store

with make_session() as session:
    resolver = Resolver(session, create=True)
    store = load_entity_file_store(Path("entities.ftm.json"), resolver)
    view = store.default_view()
    for entity in view.entities():
        print(entity.caption)
```

## Interface

::: nomenklatura.store.Store

::: nomenklatura.store.Writer

::: nomenklatura.store.View

## Implementations

::: nomenklatura.store.MemoryStore

::: nomenklatura.store.sql.SQLStore

::: nomenklatura.store.load_entity_file_store
