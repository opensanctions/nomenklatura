import os

from messytables.any import AnyTableSet
from messytables import headers_guess, headers_processor
from messytables import offset_processor

from nomenklatura.core import app, db, celery
from nomenklatura.exc import NotFound
from nomenklatura.util import flush_cache
from nomenklatura.model import Dataset, Entity, Alias, Account, Upload


def upload_file(dataset, file_, account):
    upload = Upload.create(dataset, account,
                           file_.filename, file_.mimetype)
    file_.save(upload.path)
    db.session.commit()
    return upload


def get_map_metadata(dataset, id):
    metadata, row_set = parse_upload(dataset, id)
    headers = detect_headers(row_set)
    return {
        'dataset': dataset,
        'id': id,
        'sample': list(row_set.sample)[:5],
        'headers': headers,
        'filename': metadata.filename
    }


def parse_upload(dataset, id):
    upload = Upload.by_id(id)
    if upload is None:
        return None, None
    fh = open(upload.path, 'rb')
    fn, ext = os.path.splitext(upload.filename)
    ext = ext[1:] if ext else None
    table_set = AnyTableSet.from_fileobj(fh,
            mimetype=upload.mimetype,
            extension=ext[1:])
    return upload, table_set.tables[0]


def detect_headers(row_set):
    offset, headers = headers_guess(row_set.sample)
    row_set.register_processor(headers_processor(headers))
    row_set.register_processor(offset_processor(offset + 1))
    return headers


@celery.task
def import_upload(dataset_name, id, account_id,
                  entity_col, alias_col):
    dataset = Dataset.find(dataset_name)
    account = Account.by_id(account_id)
    metadata, row_set = parse_upload(dataset, id)
    headers = detect_headers(row_set)
    for row in row_set:
        data = dict([(c.column, c.value) for c in row])
        entity = data.pop(entity_col) if entity_col else None
        alias = data.pop(alias_col) if alias_col else None
        if alias_col and alias is not None and len(alias) and alias != entity:
            d = {'name': alias, 'data': data}
            alias_obj = Alias.lookup(dataset, d, account,
                                     match_entity=False)
            data = {}
        if entity_col and entity is not None and len(entity):
            d = {'name': entity, 'data': data}
            entity_obj = Entity.by_name(dataset, entity)
            if entity_obj is None:
                entity_obj = Entity.create(dataset, d, account)
            entity_obj.data = data
        if alias_col and entity_col:
            alias_obj.match(dataset, {'choice': entity_obj.id}, account)
    db.session.commit()
    flush_cache(dataset)
