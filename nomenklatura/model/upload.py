import os
from datetime import datetime
from tablib import Dataset as TablibDataset

from nomenklatura.exc import NotFound
from nomenklatura.core import db, app


class Upload(db.Model):
    __tablename__ = 'upload'

    id = db.Column(db.Integer, primary_key=True)
    mimetype = db.Column(db.Unicode)
    filename = db.Column(db.Unicode)
    data = db.deferred(db.Column(db.LargeBinary))
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow)


    def to_dict(self):
        data = {
            'id': self.id,
            'mimetype': self.mimetype,
            'filename': self.filename,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'headers': None,
            'sample': None,
            'rows': 0
        }
        if self.tab is not None:
            data['headers'] = self.tab.headers
            data['sample'] = self.tab.dict[:5]
            data['rows'] = self.tab.height
        data['parse_error'] = self._tab_error
        return data

    @property
    def tab(self):
        if not hasattr(self, '_tab'):
            try:
                self._tab = TablibDataset()
                self._tab.csv = self.data
                self._tab_error = None
            except Exception, e:
                self._tab = None
                self._tab_error = unicode(e)
        return self._tab

    @classmethod
    def by_id(cls, id):
        return cls.query.filter_by(id=id).first()

    @classmethod
    def find(cls, id):
        upload = cls.by_id(id)
        if upload is None:
            raise NotFound("No such upload: %s" % id)
        return upload

    @classmethod
    def all(cls):
        return cls.query

    @classmethod
    def create(cls, dataset, account, file_):
        upload = cls()
        upload.dataset = dataset
        upload.creator = account
        upload.mimetype = file_.mimetype
        upload.filename = file_.filename
        upload.filename = file_.filename
        upload.data = file_.read()
        db.session.add(upload)
        db.session.flush()
        return upload
