from sqlalchemy import func, select, and_
from sqlalchemy.sql import cast

from nomenklatura.model.entity import Entity
from nomenklatura.model.text import normalize
from nomenklatura.core import db


class Matches(object):

    def __init__(self, q):
        self.lq = self.q = q

    def limit(self, l):
        self.lq = self.lq.limit(l)
        return self

    def offset(self, o):
        self.lq = self.lq.offset(o)
        return self

    def count(self):
        rp = db.engine.execute(self.q.alias('count').count())
        (count,) = rp.fetchone()
        return count

    def __iter__(self):
        rp = db.engine.execute(self.lq)
        rows = rp.fetchall()
        ids = [r[0] for r in rows]
        entities = Entity.id_map(ids)
        for (id, score) in rows:
            yield {'score': int(score), 'entity': entities.get(id)}


def find_matches(dataset, text, exclude=None):
    entities = Entity.__table__
    match_text = normalize(text, dataset)[:254]

    # select text column and apply necesary transformations
    text_field = entities.c.name
    if dataset.normalize_text:
        text_field = entities.c.normalized
    if dataset.ignore_case:
        text_field = func.lower(text_field)
    text_field = func.left(text_field, 254)
    
    # calculate the difference percentage
    l = func.greatest(1.0, func.least(len(match_text), func.length(text_field)))
    score = func.greatest(0.0, ((l - func.levenshtein(text_field, match_text)) / l) * 100.0)
    score = score.label('score')

    # coalesce the canonical identifier
    id_ = func.coalesce(entities.c.canonical_id, entities.c.id)
    id_ = func.distinct(id_).label('id')

    # apply filters
    filters = [entities.c.dataset_id==dataset.id,
               entities.c.invalid==False]
    if not dataset.match_aliases:
        filters.append(entities.c.canonical_id==None)
    if exclude is not None:
        filters.append(id_!=exclude)

    q = select([id_, score], and_(*filters), [entities],
        order_by=[score.desc()])
    return Matches(q)
