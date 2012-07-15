from datetime import datetime

from linkspotting.core import db

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

