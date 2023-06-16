import tempfile
from pathlib import Path
from followthemoney import model

from nomenklatura.resolver import Resolver
from nomenklatura.judgement import Judgement
from nomenklatura.store.level import LevelDBStore
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


def test_leveldb_store_basics(test_dataset: Dataset):
    path = Path(tempfile.mkdtemp()) / "leveldb"
    resolver = Resolver[CompositeEntity]()
    store = LevelDBStore(test_dataset, resolver, path)
    entity = CompositeEntity.from_dict(model, PERSON, default_dataset=test_dataset.name)
    entity_ext = CompositeEntity.from_dict(
        model, PERSON_EXT, default_dataset=test_dataset.name
    )
    assert len(list(store.view(test_dataset).entities())) == 0
    writer = store.writer()
    writer.add_entity(entity)
    writer.flush()
    assert len(list(store.view(test_dataset).entities())) == 1
    writer.add_entity(entity_ext)
    writer.flush()
    assert len(list(store.view(test_dataset).entities())) == 2

    merged_id = resolver.decide(
        "john-doe",
        "john-doe-2",
        judgement=Judgement.POSITIVE,
        user="test",
    )
    store.update(merged_id)
    assert len(list(store.view(test_dataset).entities())) == 1
