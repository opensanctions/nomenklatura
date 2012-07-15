from datetime import datetime

from linkspotting.core import db

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

