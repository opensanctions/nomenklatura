from datetime import datetime

from formencode import Schema, All, Invalid, validators
from formencode import FancyValidator
from sqlalchemy.orm import joinedload_all

from nomenklatura.core import db
from nomenklatura.model.common import JsonType, DataBlob


class ValueState():

    def __init__(self, dataset, value):
        self.dataset = dataset
        self.value = value


class AvailableValue(FancyValidator):

    def _to_python(self, value, state):
        v = Value.by_value(state.dataset, value)
        if v is None:
            return value
        if state.value and v.id == state.value.id:
            return value
        raise Invalid('Value already exists.', value, None)

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
    value = All(validators.String(min=0, max=5000), AvailableValue())
    data = DataBlob(if_missing={}, if_empty={})

class ValueMergeSchema(Schema):
    allow_extra_fields = True
    target = MergeableValue()

class Value(db.Model):
    __tablename__ = 'value'

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Unicode)
    data = db.Column(JsonType, default=dict)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    links = db.relationship('Link', backref='value',
                             lazy='dynamic')
    links_static = db.relationship('Link')

    def as_dict(self):
        return {
            'id': self.id, 
            'value': self.value, 
            'created_at': self.created_at,
            'creator': self.creator.as_dict(),
            'updated_at': self.updated_at,
            'dataset': self.dataset.name,
            'data': self.data,
            'link_count': self.links.count()
            }

    @property
    def display_value(self):
        return self.value

    @classmethod
    def by_value(cls, dataset, value):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(value=value).first()

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
    def all(cls, dataset, query=None, eager_links=False):
        q = cls.query.filter_by(dataset=dataset)
        if query is not None and len(query.strip()):
            q = q.filter(cls.value.ilike('%%%s%%' % query.strip()))
        if eager_links:
            q = q.options(joinedload_all(cls.links_static))
        return q

    @classmethod
    def create(cls, dataset, data, account):
        state = ValueState(dataset, None)
        data = ValueSchema().to_python(data, state)
        value = cls()
        value.dataset = dataset
        value.creator = account
        value.value = data['value']
        value.data = data['data']
        db.session.add(value)
        db.session.flush()
        return value

    def update(self, data, account):
        state = ValueState(self.dataset, self)
        data = ValueSchema().to_python(data, state)
        self.creator = account
        self.value = data['value']
        self.data = data['data']
        db.session.add(self)

    def merge_into(self, data, account):
        from nomenklatura.model.link import Link
        state = ValueState(self.dataset, self)
        data = ValueMergeSchema().to_python(data, state)
        target = data.get('target')
        for link in self.links:
            link.value = target
        link = Link()
        link.key = self.value
        link.creator = self.creator
        link.matcher = account
        link.value = target
        link.dataset = self.dataset
        link.is_matched = True
        db.session.delete(self)
        db.session.add(link)
        db.session.commit()
        return target

