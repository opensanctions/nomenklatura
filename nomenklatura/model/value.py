from datetime import datetime

from formencode import Schema, All, Invalid, validators
from formencode import FancyValidator
from sqlalchemy.orm import joinedload_all

from nomenklatura.core import db
from nomenklatura.model.common import JsonType, DataBlob
from nomenklatura.util import flush_cache, add_candidate_to_cache


class ValueState():

    def __init__(self, dataset, value):
        self.dataset = dataset
        self.value = value


class AvailableName(FancyValidator):

    def _to_python(self, name, state):
        v = Value.by_name(state.dataset, name)
        if v is None:
            return name
        if state.value and v.id == state.value.id:
            return name
        raise Invalid('Value already exists.', name, None)

class MergeableValue(FancyValidator):

    def _to_python(self, value, state):
        other = Value.by_id(state.dataset, value)
        if other is None:
            raise Invalid('Value does not exist.', value, None)
        if other == state.value:
            raise Invalid('Values are identical.', value, None)
        if other.dataset != state.dataset:
            raise Invalid('Value belongs to a different dataset.',
                          value, None)
        return other

class ValueSchema(Schema):
    allow_extra_fields = True
    name = All(validators.String(min=0, max=5000), AvailableName())
    data = DataBlob(if_missing={}, if_empty={})

class ValueMergeSchema(Schema):
    allow_extra_fields = True
    target = MergeableValue()

class Value(db.Model):
    __tablename__ = 'entity'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    data = db.Column(JsonType, default=dict)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    links = db.relationship('Link', backref='value',
                             lazy='dynamic')
    links_static = db.relationship('Link')

    def as_dict(self, shallow=False):
        d = {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            }
        if not shallow:
            d['creator'] = self.creator.as_dict()
            d['dataset'] = self.dataset.name,
            d['data'] = self.data,
        return d

    @property
    def display_name(self):
        return self.name

    @classmethod
    def by_name(cls, dataset, name):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(name=name).first()

    @classmethod
    def by_id(cls, dataset, id):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(id=id).first()

    @classmethod
    def id_map(cls, dataset, ids):
        values = {}
        for value in cls.query.filter_by(dataset=dataset).\
                filter(cls.id.in_(ids)):
            values[value.id] = value
        return values

    @classmethod
    def find(cls, dataset, id):
        value = cls.by_id(dataset, id)
        if value is None:
            raise NotFound("No such value ID: %s" % id)
        return value

    @classmethod
    def all(cls, dataset, query=None, eager_links=False, eager=False):
        q = cls.query.filter_by(dataset=dataset)
        if query is not None and len(query.strip()):
            q = q.filter(cls.name.ilike('%%%s%%' % query.strip()))
        if eager_links:
            q = q.options(joinedload_all(cls.links_static))
        if eager:
            q = q.options(db.joinedload('dataset'))
            q = q.options(db.joinedload('creator'))
        return q

    @classmethod
    def create(cls, dataset, data, account):
        state = ValueState(dataset, None)
        data = ValueSchema().to_python(data, state)
        value = cls()
        value.dataset = dataset
        value.creator = account
        value.name = data['name']
        value.data = data['data']
        db.session.add(value)
        db.session.flush()
        add_candidate_to_cache(dataset, value.name, value.id)
        return value

    def update(self, data, account):
        state = ValueState(self.dataset, self)
        data = ValueSchema().to_python(data, state)
        self.creator = account
        self.name = data['name']
        self.data = data['data']
        flush_cache(self.dataset)
        db.session.add(self)

    def merge_into(self, data, account):
        from nomenklatura.model.link import Link
        state = ValueState(self.dataset, self)
        data = ValueMergeSchema().to_python(data, state)
        target = data.get('target')
        print [target]
        for link in self.links:
            link.value = target
        link = Link()
        link.key = self.name
        link.creator = self.creator
        link.matcher = account
        link.value = target
        link.dataset = self.dataset
        link.is_matched = True
        db.session.delete(self)
        db.session.add(link)
        db.session.commit()
        flush_cache(self.dataset)
        return target

