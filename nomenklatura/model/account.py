from datetime import datetime

from nomenklatura.core import db
from nomenklatura.model.common import make_key


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
    uploads = db.relationship('Upload', backref='creator',
                               lazy='dynamic')
    entities_created = db.relationship('Entity', backref='creator',
                               lazy='dynamic')

    def to_dict(self):
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
        self.login = data['login']
        self.email = data.get('email')
        db.session.add(self)


