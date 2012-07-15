from datetime import datetime

from linkspotting.core import db

class Link(db.Model):
    __tablename__ = 'link'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Unicode)
    is_matched = db.Column(db.Boolean)
    is_invalid = db.Column(db.Boolean)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    value_id = db.Column(db.Integer, db.ForeignKey('value.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    def as_dict(self):
        return {
            'id': self.id,
            'key': self.key,
            'value': self.value.as_dict() if self.value else None,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'is_matched': self.is_matched,
            'is_invalid': self.is_invalid,
            'dataset': self.dataset.name
            }

    @classmethod
    def by_key(cls, dataset, key):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(key=key).first()

    @classmethod
    def by_id(cls, dataset, id):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(id=id).first()

    @classmethod
    def all(cls, dataset):
        return cls.query.filter_by(dataset=dataset)

    @classmethod
    def all_matched(cls, dataset):
        return cls.all(dataset).\
                filter_by(is_matched=True)

    @classmethod
    def all_unmatched(cls, dataset):
        return cls.all(dataset).\
                filter_by(is_matched=False)

    @classmethod
    def find(cls, dataset, id):
        link = cls.by_id(dataset, id)
        if link is None:
            raise NotFound("No such link ID: %s" % id)
        return link

