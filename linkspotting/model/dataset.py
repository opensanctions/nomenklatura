from datetime import datetime

from formencode import Schema, validators

from linkspotting.core import db
from linkspotting.model.common import Name
from linkspotting.exc import NotFound


class DatasetNewSchema(Schema):
    name = Name(not_empty=True)
    label = validators.String(min=3, max=255)


class Dataset(db.Model):
    __tablename__ = 'dataset'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    label = db.Column(db.Unicode)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    values = db.relationship('Value', backref='dataset',
                             lazy='dynamic')
    links = db.relationship('Link', backref='dataset',
                             lazy='dynamic')

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
        db.session.commit()
        return dataset

