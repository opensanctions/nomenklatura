from datetime import datetime

from formencode import Schema, All, Invalid, validators
from formencode import FancyValidator

from linkspotting.core import db


class ValueState():

    def __init__(self, dataset, value):
        self.dataset = dataset
        self.value = value


class AvailableValue(FancyValidator):

    def _to_python(self, value, state):
        v = Value.by_value(state.dataset, value)
        if v is None:
            return value
        if v.id == state.value.id:
            return value
        raise Invalid('Value already exists.', value, None)


class ValueSchema(Schema):
    value = All(validators.String(min=0, max=5000), AvailableValue())


class Value(db.Model):
    __tablename__ = 'value'

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Unicode)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    links = db.relationship('Link', backref='value',
                             lazy='dynamic')

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
    def find(cls, dataset, id):
        value = cls.by_id(dataset, id)
        if value is None:
            raise NotFound("No such value ID: %s" % id)
        return value

    @classmethod
    def all(cls):
        return cls.query

    @classmethod
    def create(cls, dataset, data):
        state = ValueState(dataset, None)
        data = ValueSchema().to_python(data, state)
        value = cls()
        value.dataset = dataset
        value.value = data['value']
        db.session.add(value)
        db.session.flush()
        return value

    def update(self, data):
        state = ValueState(self.dataset, self)
        data = ValueSchema().to_python(data, state)
        self.value = data['value']
        db.session.add(self)


