from nomenklatura.core import db
from nomenklatura.core import celery as app
from nomenklatura.model import Dataset, Entity, Account, Upload

@app.task
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
