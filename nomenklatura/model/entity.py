from datetime import datetime

from formencode import Schema, All, Invalid, validators
from formencode import FancyValidator
from sqlalchemy.orm import joinedload_all

from nomenklatura.core import db
from nomenklatura.exc import NotFound
from nomenklatura.model.common import JsonType, DataBlob


class EntityState():

    def __init__(self, dataset, entity):
        self.dataset = dataset
        self.entity = entity


class AvailableName(FancyValidator):

    def _to_python(self, name, state):
        entity = Entity.by_name(state.dataset, name)
        if entity is None:
            return name
        if state.entity and entity.id == state.entity.id:
            return name
        raise Invalid('Entity already exists.', name, None)


class MergeableEntity(FancyValidator):

    def _to_python(self, value, state):
        entity = Entity.by_id(value)
        if entity is None:
            raise Invalid('Entity does not exist.', value, None)
        if entity == state.entity:
            raise Invalid('Entities are identical.', value, None)
        if entity.dataset != state.dataset:
            raise Invalid('Entity belongs to a different dataset.',
                          value, None)
        return entity


class EntitySchema(Schema):
    allow_extra_fields = True
    name = All(validators.String(min=0, max=5000), AvailableName())
    data = DataBlob(if_missing={}, if_empty={})


class EntityMergeSchema(Schema):
    allow_extra_fields = True
    target = MergeableEntity()


class Entity(db.Model):
    __tablename__ = 'entity'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    data = db.Column(JsonType, default=dict)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    aliases = db.relationship('Alias', backref='entity',
                             lazy='dynamic')
    aliases_static = db.relationship('Alias')

    def to_dict(self, shallow=False):
        d = {
            'id': self.id,
            'name': self.name,
            'dataset': self.dataset.name,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }
        if not shallow:
            d['creator'] = self.creator.to_dict()
            d['data'] = self.data
            d['num_aliases'] = self.aliases.count()
        return d

    def to_row(self):
        row = self.data.copy()
        row.update(self.as_dict(shallow=True))
        return row

    @property
    def display_name(self):
        return self.name

    @classmethod
    def by_name(cls, dataset, name):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(name=name).first()

    @classmethod
    def by_id(cls, id):
        return cls.query.filter_by(id=id).first()

    @classmethod
    def id_map(cls, dataset, ids):
        entities = {}
        for entity in cls.query.filter_by(dataset=dataset).\
                filter(cls.id.in_(ids)):
            entities[entity.id] = entity
        return entities

    @classmethod
    def find(cls, dataset, id):
        entity = cls.by_id(dataset, id)
        if entity is None:
            raise NotFound("No such value ID: %s" % id)
        return entity

    @classmethod
    def all(cls, dataset=None, query=None, eager_aliases=False, eager=False):
        q = cls.query
        if dataset is not None:
            q = q.filter_by(dataset=dataset)
        if query is not None and len(query.strip()):
            q = q.filter(cls.name.ilike('%%%s%%' % query.strip()))
        if eager_aliases:
            q = q.options(joinedload_all(cls.aliases_static))
        if eager:
            q = q.options(db.joinedload('dataset'))
            q = q.options(db.joinedload('creator'))
        return q

    @classmethod
    def create(cls, dataset, data, account):
        state = EntityState(dataset, None)
        data = EntitySchema().to_python(data, state)
        entity = cls()
        entity.dataset = dataset
        entity.creator = account
        entity.name = data['name']
        entity.data = data['data']
        db.session.add(entity)
        db.session.flush()
        return entity

    def update(self, data, account):
        state = EntityState(self.dataset, self)
        data = EntitySchema().to_python(data, state)
        self.creator = account
        self.name = data['name']
        self.data = data['data']
        db.session.add(self)

    def merge_into(self, data, account):
        from nomenklatura.model.alias import Alias
        state = EntityState(self.dataset, self)
        data = EntityMergeSchema().to_python(data, state)
        target = data.get('target')
        for alias in self.aliases:
            alias.entity = target
        alias = Alias()
        alias.name = self.name
        alias.creator = self.creator
        alias.matcher = account
        alias.entity = target
        alias.dataset = self.dataset
        alias.is_matched = True
        db.session.delete(self)
        db.session.add(alias)
        db.session.commit()
        return target
