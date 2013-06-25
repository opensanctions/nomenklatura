import os
from datetime import datetime

from nomenklatura.core import db, app


class Upload(db.Model):
    __tablename__ = 'upload'

    id = db.Column(db.Integer, primary_key=True)
    mimetype = db.Column(db.Unicode)
    filename = db.Column(db.Unicode)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    def as_dict(self):
        return {
            'id': self.id,
            'mimetype': self.mimetype,
            'filename': self.filename,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @property
    def path(self):
        prefix = app.config.get('UPLOAD_PREFIX', '/tmp/nomenklatura')
        prefix = os.path.join(prefix, self.dataset.name)
        if not os.path.isdir(prefix):
            os.makedirs(prefix)
        return os.path.join(prefix, str(self.id))

    @classmethod
    def by_id(cls, id):
        return cls.query.filter_by(id=id).first()

    @classmethod
    def all(cls):
        return cls.query

    @classmethod
    def create(cls, dataset, account, filename, mimetype):
        upload = cls()
        upload.dataset = dataset
        upload.creator = account
        upload.mimetype = mimetype
        upload.filename = filename
        db.session.add(upload)
        db.session.flush()
        return upload
