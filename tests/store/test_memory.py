from followthemoney import model

from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.store import MemoryStore
from nomenklatura.dataset import Dataset
from nomenklatura.entity import CompositeEntity

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


def test_basic_store(test_dataset: Dataset):
    resolver = Resolver[CompositeEntity]()
    store = MemoryStore(test_dataset, resolver)
    entity = CompositeEntity.from_dict(model, PERSON, default_dataset=test_dataset.name)
    entity_ext = CompositeEntity.from_dict(
        model, PERSON_EXT, default_dataset=test_dataset.name
    )
    assert len(store.stmts) == 0
    writer = store.writer()
    writer.add_entity(entity)
    writer.flush()
    assert len(store.stmts) == 1
    assert len(list(store.view(test_dataset).entities())) == 1
    writer.add_entity(entity_ext)
    writer.flush()
    assert len(store.stmts) == 2
    assert len(list(store.view(test_dataset).entities())) == 2

    merged_id = resolver.decide(
        "john-doe",
        "john-doe-2",
        judgement=Judgement.POSITIVE,
        user="test",
    )
    store.update(merged_id)
    assert len(store.stmts) == 1
    assert len(list(store.view(test_dataset).entities())) == 1
