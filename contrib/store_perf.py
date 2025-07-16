from zavod.logs import get_logger
from zavod.meta import get_catalog, Dataset

# from zavod.runtime.versions import get_latest
from zavod.integration.dedupe import get_dataset_linker
# from zavod.archive import iter_dataset_statements
# from zavod.entity import Entity

from zavod.store import get_store

# from nomenklatura.versions import Version
# from nomenklatura.store.versioned import (
#     VersionedRedisStore,
#     VersionedRedisView,
#     VersionedRedisWriter,
# )

log = get_logger("store_perf")

catalog = get_catalog()
scope = catalog.require("sanctions")
resolver = get_dataset_linker(scope)


def get_leveldb_view(scope: Dataset):
    store = get_store(scope, resolver)
    store.sync()
    return store.view(scope)


# def get_versioned_view(scope: Dataset):
#     # docker run -it -p 6666:6666 --mount=type=bind,source=/Users/pudo/Data/kvrocks,target=/data apache/kvrocks --bind 0.0.0.0 --dir /data
#     from nomenklatura import settings

#     settings.REDIS_URL = "redis://localhost:6666/0"

#     store = VersionedRedisStore(scope, resolver)
#     for dataset in scope.datasets:
#         if dataset.is_collection:
#             continue
#         ds_version = get_latest(dataset.name)
#         if ds_version is None:
#             continue
#         # print(dataset.name, ds_version)
#         version = str(ds_version)
#         if store.has_version(dataset, version):
#             continue
#         log.info("Loading dataset...", dataset=dataset.name, version=version)
#         writer = store.writer(dataset, version)
#         for stmt in iter_dataset_statements(dataset):
#             writer.add_statement(stmt)
#         writer.flush()
#         writer.close()
#     return store.view(scope)


# def get_zahir_view(scope: Dataset):
#     from zahirclient.client import ZahirClient

#     client = ZahirClient(Entity, scope, "http://localhost:6674")
#     server_versions = client.get_datasets()
#     for dataset in scope.datasets:
#         if dataset.is_collection:
#             continue
#         ds_version = get_latest(dataset.name)
#         if ds_version is None:
#             continue
#         latest_version = str(ds_version)
#         server_version = server_versions.get(dataset.name, None)
#         if latest_version == server_version:
#             # log.info(
#             #     "Dataset is up to date", dataset=dataset.name, version=latest_version
#             # )
#             continue
#         log.info(
#             "Syncing dataset...",
#             dataset=dataset.name,
#             latest_version=latest_version,
#             server_version=server_version,
#         )
#         client.write_statements(latest_version, iter_dataset_statements(dataset))
#         client.release_dataset(dataset.name, latest_version)


# Q96971766

# entity = view.get_entity("Q96971766")
# print(entity, list(entity.statements))
# store.sync(clear=True)

# view = store.default_view()
view = get_leveldb_view(scope)
for idx, ent in enumerate(view.entities()):
    if idx > 0 and idx % 10_000 == 0:
        log.info("Loading entities...", entities=idx, scope=scope.name)
        # for i in range(5):
        #     ent.to_nested_dict(view)
