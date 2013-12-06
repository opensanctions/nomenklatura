from formencode import Invalid

from nomenklatura.core import db
from nomenklatura.core import celery as app
from nomenklatura.model import Dataset, Entity, Account, Upload


def apply_mapping(row, mapping):
    out = {'attributes': {}, 'reviewed': mapping['reviewed']}
    for column, prop in mapping['columns'].items():
        value = row.get(column)
        if value is None or not len(value.strip()):
            continue
        if prop.startswith('attributes.'):
            a, prop = prop.split('.', 1)
            out[a][prop] = value
        else:
            out[prop] = value
    return out


@app.task
def import_upload(upload_id, account_id, mapping):
    upload = Upload.all().filter_by(id=upload_id).first()
    account = Account.by_id(account_id)
    mapped = mapping['columns'].values()

    rows = [apply_mapping(r, mapping) for r in upload.tab.dict]
    # put aliases second.
    rows = sorted(rows, key=lambda r: 2 if r.get('canonical') else 1)

    for row in rows:
        try:
            entity = None
            if row.get('id'):
                entity = Entity.by_id(row.get('id'))
            if entity is None:
                entity = Entity.by_name(upload.dataset, row.get('name'))
            if entity is None:
                entity = Entity.create(upload.dataset, row, account)

            # restore some defaults: 
            if entity.canonical_id and 'canonical' not in mapped:
                row['canonical'] = entity.canonical_id
            if entity.invalid and 'invalid' not in mapped:
                row['invalid'] = entity.invalid 

            if entity.attributes:
                attributes = entity.attributes.copy()
            else:
                attributes = {}
            attributes.update(row['attributes'])
            row['attributes'] = attributes

            entity.update(row, account)
            #print entity
            db.session.commit()
        except Invalid, inv:
            # TODO: logging. 
            print inv
