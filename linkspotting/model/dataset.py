from datetime import datetime

from formencode import Schema, All, Invalid, validators

from linkspotting.core import db
from linkspotting.model.common import Name, FancyValidator
from linkspotting.exc import NotFound

class AvailableDatasetName(FancyValidator):

    def _to_python(self, value, state):
        if Dataset.by_name(value) is None:
            return value
        raise Invalid('Dataset already exists.', value, None)

class DatasetNewSchema(Schema):
    name = All(AvailableDatasetName(), Name(not_empty=True))
    label = validators.String(min=3, max=255)

class DatasetEditSchema(Schema):
    label = validators.String(min=3, max=255)

class Dataset(db.Model):
    __tablename__ = 'dataset'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    label = db.Column(db.Unicode)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    values = db.relationship('Value', backref='dataset',
                             lazy='dynamic')
    links = db.relationship('Link', backref='dataset',
                             lazy='dynamic')

    def as_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'label': self.label,
            'created_at': self.created_at,
            'updated_at': self.updated_at
            }

    @classmethod
    def by_name(cls, name):
        return cls.query.filter_by(name=name).first()

    @classmethod
    def find(cls, name):
        dataset = cls.by_name(name)
        if dataset is None:
            raise NotFound("No such dataset: %s" % name)
        return dataset

    @classmethod
    def all(cls):
        return cls.query

    @classmethod
    def create(cls, data):
        data = DatasetNewSchema().to_python(data)
        dataset = cls()
        dataset.name = data['name']
        dataset.label = data['label']
        db.session.add(dataset)
        db.session.flush()
        return dataset

    def update(self, data):
        data = DatasetEditSchema().to_python(data)
        self.label = data['label']
        db.session.add(self)
