from datetime import datetime
from uuid import uuid4

from nomenklatura.core import db
from nomenklatura.model.common import JsonType, DataBlob


def make_key():
    return unicode(uuid4())


class Account(db.Model):
    __tablename__ = 'account'

    id = db.Column(db.Integer, primary_key=True)
    github_id = db.Column(db.Integer)
    login = db.Column(db.Unicode)
    email = db.Column(db.Unicode)
    api_key = db.Column(db.Unicode, default=make_key)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    datasets = db.relationship('Dataset', backref='owner',
                               lazy='dynamic')
    values_created = db.relationship('Value', backref='creator',
                               lazy='dynamic')
    links_created = db.relationship('Link', backref='creator',
                        primaryjoin='Link.creator_id==Account.id',
                               lazy='dynamic')
    links_matched = db.relationship('Link', backref='matcher',
                        primaryjoin='Link.matcher_id==Account.id',
                               lazy='dynamic')

    def as_dict(self):
        return {
            'id': self.id,
            'github_id': self.github_id,
            'login': self.login,
            'created_at': self.created_at, 
            'updated_at': self.updated_at,
            }

    @classmethod
    def by_id(cls, id):
        return cls.query.filter_by(id=id).first()

    @classmethod
    def by_api_key(cls, api_key):
        return cls.query.filter_by(api_key=api_key).first()

    @classmethod
    def by_github_id(cls, github_id):
        return cls.query.filter_by(github_id=github_id).first()

    @classmethod
    def create(cls, data):
        account = cls()
        account.github_id = data['id']
        account.login = data['login']
        account.email = data.get('email')
        db.session.add(account)
        db.session.flush()
        return account

    def update(self, data):
        account.login = data['login']
        account.email = data.get('email')
        db.session.add(self)


