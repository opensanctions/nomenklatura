from hashlib import sha1
from time import time
import os
from tempfile import mkstemp

from messytables.any import AnyTableSet
from messytables import headers_guess, headers_processor, \
        offset_processor

from nomenklatura.core import s3, app, db, celery
from nomenklatura.exc import NotFound
from nomenklatura.model import Dataset, Link, Value, Account

def get_bucket():
    return s3.create_bucket(app.config['S3_BUCKET'])

def key_name(dataset, sig):
    return "%s/%s" % (dataset.name, sig)

def upload_file(dataset, file_):
    fn = file_.filename.encode('ascii', 'replace')
    sig = sha1(fn + str(time())).hexdigest()
    key = get_bucket().new_key(key_name(dataset, sig))
    fh, tmp = mkstemp()
    file_.save(tmp)
    key.set_metadata('filename', file_.filename)
    key.set_metadata('mimetype', file_.mimetype)
    key.set_contents_from_filename(tmp)
    os.unlink(tmp)
    return sig

def get_key(dataset, sig):
    key = get_bucket().get_key(key_name(dataset, sig))
    if not key:
        raise NotFound()
    return key

def get_map_metadata(dataset, sig):
    metadata, row_set = parse_upload(dataset, sig)
    headers = detect_headers(row_set)
    return {
        'dataset': dataset,
        'sig': sig,
        'sample': list(row_set.sample)[:5],
        'headers': headers,
        'filename': metadata.get('filename')
        }

def parse_upload(dataset, sig):
    key = get_key(dataset, sig)
    fn, ext = os.path.splitext(key.metadata.get('filename'))
    ext = ext[1:] if ext else None
    table_set = AnyTableSet.from_fileobj(key,
            mimetype=key.metadata.get('mimetype'),
            extension=ext[1:])
    return key.metadata, table_set.tables[0]

def detect_headers(row_set):
    offset, headers = headers_guess(row_set.sample)
    row_set.register_processor(headers_processor(headers))
    row_set.register_processor(offset_processor(offset + 1))
    return headers


@celery.task
def import_upload(dataset_name, sig, account_id,
        value_col, link_col):
    dataset = Dataset.find(dataset_name)
    account = Account.by_id(account_id)
    metadata, row_set = parse_upload(dataset, sig)
    headers = detect_headers(row_set)
    for row in row_set:
        data = dict([(c.column, c.value) for c in row])
        value = data.pop(value_col) if value_col else None
        link = data.pop(link_col) if link_col else None
        if link_col:
            d = {'key': link, 'data': data}
            link_obj = Link.lookup(dataset, d, account,
                            match_value=False)
            data = {}
        if value_col:
            d = {'value': value, 'data': data}
            value_obj = Value.by_value(dataset, value)
            if value_obj is None:
                value_obj = Value.create(dataset,
                        d, account)
            value_obj.data = data
        if link_col and value_col:
            link_obj.match(dataset, {'choice': value_obj.id},
                    account)
        db.session.commit()

