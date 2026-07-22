from followthemoney import Dataset, StatementEntity, registry

from nomenklatura.enrich.common import BaseEnricher

dataset = Dataset.make({"name": "test", "title": "Test"})


def make_entity(schema: str, topics: list = []) -> StatementEntity:
    properties = {"name": ["Thing"], "topics": topics}
    data = {"schema": schema, "id": "xxx", "properties": properties}
    return StatementEntity.from_data(dataset, data)


def test_filter_topics_resolved(cache_factory):
    cache = cache_factory(dataset)
    enricher = BaseEnricher(dataset, cache, {"topics": ["sanction", "crime.boss"]})
    assert enricher.filter_topics == {"sanction", "crime.boss"}

    enricher = BaseEnricher(dataset, cache, {})
    assert enricher.filter_topics == set()

    # "all" expands to every topic and doesn't remain in the set as a literal.
    enricher = BaseEnricher(dataset, cache, {"topics": ["all"]})
    assert enricher.filter_topics == set(registry.topic.names.keys())


def test_filter_entity_topics(cache_factory):
    cache = cache_factory(dataset)
    enricher = BaseEnricher(dataset, cache, {"topics": ["sanction"]})
    assert enricher._filter_entity(make_entity("Person", ["sanction"]))
    assert not enricher._filter_entity(make_entity("Person", ["crime.boss"]))
    assert not enricher._filter_entity(make_entity("Person"))

    # No topics configured: nothing is filtered on topic.
    enricher = BaseEnricher(dataset, cache, {})
    assert enricher._filter_entity(make_entity("Person"))

    # "all" passes any tagged entity, but not untagged ones.
    enricher = BaseEnricher(dataset, cache, {"topics": ["all"]})
    assert enricher._filter_entity(make_entity("Person", ["crime.boss"]))
    assert not enricher._filter_entity(make_entity("Person"))


def test_filter_entity_schemata(cache_factory):
    cache = cache_factory(dataset)
    enricher = BaseEnricher(dataset, cache, {"schemata": ["Person"]})
    assert enricher._filter_entity(make_entity("Person"))
    assert not enricher._filter_entity(make_entity("Company"))
