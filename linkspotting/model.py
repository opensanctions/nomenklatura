from datetime import datetime

from linkspotting.core import db

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


class Value(db.Model):
    __tablename__ = 'value'

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Unicode)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    links = db.relationship('Link', backref='value',
                             lazy='dynamic')

    @classmethod
    def by_value(cls, dataset, value):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(value=value).first()


class Link(db.Model):
    __tablename__ = 'link'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Unicode)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    value_id = db.Column(db.Integer, db.ForeignKey('value.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    @classmethod
    def by_key(cls, dataset, key):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(key=key).first()

