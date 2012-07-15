from datetime import datetime

from formencode import Schema, validators

from linkspotting.core import db
from linkspotting.model.common import Name


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

    values = db.relationship('Values', backref='dataset',
                             lazy='dynamic')
    links = db.relationship('Link', backref='dataset',
                             lazy='dynamic')

    @classmethod
    def by_name(cls, name):
        return cls.query.filter_by(name=name).first()
    
    @classmethod
    def create(cls, data):
        data = DatasetNewSchema().to_python(data)
        dataset = cls()
        dataset.name = data['name']
        dataset.label = data['label']
        db.session.add(dataset)
        db.session.commit()
        return dataset

