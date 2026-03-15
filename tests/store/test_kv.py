import orjson
import fakeredis
from pathlib import Path
from followthemoney import model, Dataset, StatementEntity as Entity
from rigour.time import datetime_iso, utc_now

from nomenklatura.versions import Version
from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.store.kv import KVStore

DAIMLER = "66ce9f62af8c7d329506da41cb7c36ba058b3d28"
PERSON = {
    "id": "john-doe",
    "schema": "Person",
    "properties": {"name": ["John Doe"], "birthDate": ["1976"]},
}

PERSON_EXT = {
    "id": "john-doe-2",
    "schema": "Person",
    "properties": {"birthPlace": ["North Texas"]},
}


def _make_store(
    test_dataset: Dataset, resolver: Resolver[Entity]
) -> KVStore[Dataset, Entity]:
    resolver.begin()
    redis = fakeredis.FakeStrictRedis(version=6, decode_responses=False)
    return KVStore(test_dataset, resolver, db=redis)


def test_store_basics(test_dataset: Dataset, resolver: Resolver[Entity]):
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)
    entity_ext = Entity.from_data(test_dataset, PERSON_EXT)
    assert len(list(store.view(test_dataset).entities())) == 0

    version = Version.new().id
    writer = store.writer(version=version)
    ts = datetime_iso(utc_now())
    for stmt in entity.statements:
        stmt.first_seen = ts
        stmt.last_seen = ts
        writer.add_statement(stmt)
    writer.flush()
    # Not released yet — view should see nothing
    assert store.get_latest(test_dataset.name) is None
    assert len(list(store.view(test_dataset).entities())) == 0

    # Explicit release
    store.release_version(test_dataset.name, version)
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 1

    # Add both entities in a new version (latest replaces the previous)
    version_b = Version.new().id
    writer_b = store.writer(version=version_b)
    writer_b.add_entity(entity)
    writer_b.add_entity(entity_ext)
    writer_b.flush()
    store.release_version(test_dataset.name, version_b)
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 2


def test_late_binding(test_dataset: Dataset, resolver: Resolver[Entity]):
    """Statements are stored under raw entity IDs. Merging two entities via the
    resolver causes them to be assembled as a single entity at read time without
    any re-ingestion."""
    store = _make_store(test_dataset, resolver)
    entity_a = Entity.from_data(test_dataset, PERSON)
    entity_b = Entity.from_data(test_dataset, PERSON_EXT)

    version = Version.new().id
    with store.writer(version=version) as writer:
        writer.add_entity(entity_a)
        writer.add_entity(entity_b)
    store.release_version(test_dataset.name, version)

    view = store.view(test_dataset)
    assert len(list(view.entities())) == 2

    # Merge the two entities
    merged_id = resolver.decide(
        "john-doe",
        "john-doe-2",
        judgement=Judgement.POSITIVE,
        user="test",
    )
    # No store.update() needed — late binding resolves at read time
    store.update(merged_id)  # noop, but should not error

    view = store.view(test_dataset)
    entities = list(view.entities())
    assert len(entities) == 1
    entity = entities[0]
    # The merged entity should have properties from both sources
    assert "John Doe" in entity.get("name")
    assert "North Texas" in entity.get("birthPlace")

    # Point lookup by either source ID should return the merged entity
    e1 = view.get_entity("john-doe")
    e2 = view.get_entity("john-doe-2")
    assert e1 is not None
    assert e2 is not None
    assert e1.id == e2.id


def test_external_statements(test_dataset: Dataset, resolver: Resolver[Entity]):
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)

    version = Version.new().id
    with store.writer(version=version) as writer:
        for stmt in entity.statements:
            stmt = stmt.clone(external=True)
            writer.add_statement(stmt)
    store.release_version(test_dataset.name, version)

    # Non-external view should not see the entity
    view = store.view(test_dataset, external=False)
    assert view.get_entity("john-doe") is None
    assert len(list(view.entities())) == 0

    # External view should see it
    ext_view = store.view(test_dataset, external=True)
    entity = ext_view.get_entity("john-doe")
    assert entity is not None
    assert len(list(ext_view.entities())) == 1


def test_graph_query(
    donations_path: Path, test_dataset: Dataset, resolver: Resolver[Entity]
):
    store = _make_store(test_dataset, resolver)
    version = Version.new().id
    with store.writer(version=version) as writer:
        with open(donations_path, "rb") as fh:
            while line := fh.readline():
                data = orjson.loads(line)
                proxy = Entity.from_data(test_dataset, data)
                writer.add_entity(proxy)
    store.release_version(test_dataset.name, version)

    # NOTE: entities() count test is skipped because fakeredis scan_iter is
    # O(total_keys) per call, making iteration over 474 entities very slow.
    # On real KVRocks, prefix scans are O(matched_keys). Point lookups and
    # adjacency queries below exercise the same code paths.

    view = store.default_view()
    entity = view.get_entity("banana")
    assert entity is None
    assert not view.has_entity("banana")
    entity = view.get_entity(DAIMLER)
    assert entity is not None
    assert view.has_entity(DAIMLER)
    assert "Daimler" in entity.caption, entity.caption

    adjacent = list(view.get_adjacent(entity))
    assert len(adjacent) == 10, len(adjacent)
    schemata = [e.schema for (_, e) in adjacent]
    assert model.get("Payment") in schemata
    assert model.get("Address") in schemata
    assert model.get("Company") not in schemata


def test_schema_filtering(test_dataset: Dataset, resolver: Resolver[Entity]):
    store = _make_store(test_dataset, resolver)
    person = Entity.from_data(test_dataset, PERSON)
    company = Entity.from_data(
        test_dataset,
        {"id": "acme-corp", "schema": "Company", "properties": {"name": ["ACME"]}},
    )

    version = Version.new().id
    with store.writer(version=version) as writer:
        writer.add_entity(person)
        writer.add_entity(company)
    store.release_version(test_dataset.name, version)

    view = store.view(test_dataset)
    all_entities = list(view.entities())
    assert len(all_entities) == 2

    persons = list(view.entities(include_schemata=[model.get("Person")]))
    assert len(persons) == 1
    assert persons[0].schema == model.get("Person")

    companies = list(view.entities(include_schemata=[model.get("Company")]))
    assert len(companies) == 1
    assert companies[0].schema == model.get("Company")


def test_versioning(test_dataset: Dataset, resolver: Resolver[Entity]):
    store = _make_store(test_dataset, resolver)
    assert store.get_latest(test_dataset.name) is None
    assert len(store.get_history(test_dataset.name)) == 0
    entity = Entity.from_data(test_dataset, PERSON)

    # Write version A — release via store
    version_a = Version.new().id
    assert not store.has_version(test_dataset.name, version_a)
    with store.writer(version=version_a) as writer:
        writer.add_entity(entity)
    # Writer close does NOT release
    assert store.get_latest(test_dataset.name) is None
    assert store.has_version(test_dataset.name, version_a)

    store.release_version(test_dataset.name, version_a)
    assert store.get_latest(test_dataset.name) == version_a
    assert len(store.get_history(test_dataset.name)) == 1

    # Write version B
    version_b = Version.new().id + "x"
    with store.writer(version=version_b) as writer:
        writer.add_entity(entity)
    store.release_version(test_dataset.name, version_b)
    assert store.get_latest(test_dataset.name) == version_b
    assert len(store.get_history(test_dataset.name)) == 2

    # Drop version B — should fall back to A
    store.drop_version(test_dataset.name, version_b)
    assert store.get_latest(test_dataset.name) == version_a
    assert len(store.get_history(test_dataset.name)) == 1

    # Drop version A — no versions left
    store.drop_version(test_dataset.name, version_a)
    assert store.get_latest(test_dataset.name) is None
    assert len(store.get_history(test_dataset.name)) == 0
    assert len(list(store.view(test_dataset).entities())) == 0


def test_version_isolation(test_dataset: Dataset, resolver: Resolver[Entity]):
    """Views pinned to a specific version don't see data from other versions."""
    store = _make_store(test_dataset, resolver)
    person = Entity.from_data(test_dataset, PERSON)
    company = Entity.from_data(
        test_dataset,
        {"id": "acme-corp", "schema": "Company", "properties": {"name": ["ACME"]}},
    )

    version_a = Version.new().id
    with store.writer(version=version_a) as writer:
        writer.add_entity(person)
    store.release_version(test_dataset.name, version_a)

    version_b = Version.new().id + "x"
    with store.writer(version=version_b) as writer:
        writer.add_entity(company)
    store.release_version(test_dataset.name, version_b)

    # View pinned to version A sees only the person
    view_a = store.view(test_dataset, versions={test_dataset.name: version_a})
    entities_a = list(view_a.entities())
    assert len(entities_a) == 1
    assert entities_a[0].schema == model.get("Person")

    # Default view (latest = version B) sees only the company
    view_latest = store.view(test_dataset)
    entities_latest = list(view_latest.entities())
    assert len(entities_latest) == 1
    assert entities_latest[0].schema == model.get("Company")


def test_get_timestamps(test_dataset: Dataset, resolver: Resolver[Entity]):
    """get_timestamps returns {stmt_id: first_seen} for a raw entity ID."""
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)

    ts = "2025-06-15T12:00:00"
    version = Version.new().id
    with store.writer(version=version) as writer:
        for stmt in entity.statements:
            stmt.first_seen = ts
            stmt.last_seen = ts
            writer.add_statement(stmt)
    store.release_version(test_dataset.name, version)

    view = store.view(test_dataset)
    stamps = view.get_timestamps("john-doe")
    assert len(stamps) == 3
    for stmt_id, first_seen in stamps.items():
        assert first_seen == ts


def test_timestamp_backfill_via_view(test_dataset: Dataset, resolver: Resolver[Entity]):
    """The caller uses get_timestamps() on a view pinned to the previous version
    to backfill first_seen before writing new statements. This replaces zavod's
    TimeStampIndex."""
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)

    # Version 1: initial crawl with a known first_seen
    original_time = "2025-01-01T00:00:00"
    version_1 = Version.new().id
    with store.writer(version=version_1) as writer:
        for stmt in entity.statements:
            stmt.first_seen = original_time
            stmt.last_seen = original_time
            writer.add_statement(stmt)
    store.release_version(test_dataset.name, version_1)

    # Version 2: re-crawl. Caller reads timestamps from version 1, then
    # applies them before writing version 2.
    recrawl_time = "2025-06-15T12:00:00"
    prev_view = store.view(test_dataset, versions={test_dataset.name: version_1})
    stamps = prev_view.get_timestamps("john-doe")
    assert len(stamps) == 3

    version_2 = Version.new().id + "x"
    with store.writer(version=version_2) as writer:
        for stmt in entity.statements:
            stmt.first_seen = stamps.get(stmt.id, recrawl_time)
            stmt.last_seen = recrawl_time
            writer.add_statement(stmt)
    store.release_version(test_dataset.name, version_2)

    # The stored first_seen should be the ORIGINAL time
    view_2 = store.view(test_dataset, versions={test_dataset.name: version_2})
    stamps_2 = view_2.get_timestamps("john-doe")
    assert len(stamps_2) == 3
    for stmt_id, first_seen in stamps_2.items():
        assert first_seen == original_time, (
            f"Statement {stmt_id}: expected {original_time}, got {first_seen}"
        )


def test_update_is_noop(test_dataset: Dataset, resolver: Resolver[Entity]):
    """store.update() is a noop — kept for back-compat but doesn't error."""
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)

    version = Version.new().id
    with store.writer(version=version) as writer:
        writer.add_entity(entity)
    store.release_version(test_dataset.name, version)

    # Should not raise
    store.update("john-doe")
    store.update("nonexistent-id")

    # Data should be unchanged
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 1


def test_pop_raises(test_dataset: Dataset, resolver: Resolver[Entity]):
    """pop() is not supported — late binding makes it unnecessary."""
    store = _make_store(test_dataset, resolver)
    version = Version.new().id
    writer = store.writer(version=version)
    try:
        writer.pop("john-doe")
        assert False, "Expected NotImplementedError"
    except NotImplementedError:
        pass


def test_writer_close_does_not_release(
    test_dataset: Dataset, resolver: Resolver[Entity]
):
    """Closing the writer (via context manager) flushes but does not release."""
    store = _make_store(test_dataset, resolver)
    entity = Entity.from_data(test_dataset, PERSON)

    version = Version.new().id
    with store.writer(version=version) as writer:
        writer.add_entity(entity)
    # Writer is closed, data is flushed but NOT released
    assert store.get_latest(test_dataset.name) is None
    # Data exists (has_version checks for data, not release)
    assert store.has_version(test_dataset.name, version)
    # But no view can see it (no version released)
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 0

    # Now release explicitly
    store.release_version(test_dataset.name, version)
    view = store.view(test_dataset)
    assert len(list(view.entities())) == 1
