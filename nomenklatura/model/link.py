from datetime import datetime

from formencode import Schema, Invalid, validators

from nomenklatura.core import db
from nomenklatura.model.common import Name, FancyValidator
from nomenklatura.model.value import Value
from nomenklatura.matching import match as match_op

class LinkMatchState():

    def __init__(self, dataset):
        self.dataset = dataset

class ValidChoice(FancyValidator):

    def _to_python(self, value, state):
        if value == 'NEW':
            return value
        elif value == 'INVALID' and state.dataset.enable_invalid:
            return value
        value_obj = Value.by_id(state.dataset, value)
        if value_obj is not None:
            return value_obj
        raise Invalid('No such value.', value, None)

class LinkLookupSchema(Schema):
    allow_extra_fields = True
    key = validators.String(min=0, max=5000)

class LinkMatchSchema(Schema):
    allow_extra_fields = True
    value = validators.String(min=0, max=5000, if_missing='', if_empty='')
    choice = ValidChoice()

class Link(db.Model):
    __tablename__ = 'link'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.Unicode)
    is_matched = db.Column(db.Boolean, default=False)
    is_invalid = db.Column(db.Boolean, default=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    matcher_id = db.Column(db.Integer, db.ForeignKey('account.id'),
            nullable=True)
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
            'creator': self.creator.as_dict(),
            'updated_at': self.updated_at,
            'is_matched': self.is_matched,
            'matcher': self.matcher.as_dict() if self.matcher else None,
            'is_invalid': self.is_invalid,
            'dataset': self.dataset.name
            }

    @property
    def display_key(self):
        return self.key

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

    @classmethod
    def lookup(cls, dataset, data, account, readonly=False):
        data = LinkLookupSchema().to_python(data)
        value = Value.by_value(dataset, data['key'])
        if value is not None:
            return value
        link = cls.by_key(dataset, data['key'])
        if link is not None:
            return link
        choices = match_op(data['key'], dataset)
        choices = filter(lambda (c,v,s): s == 100, choices)
        if len(choices)==1:
            c, value, s = choices.pop()
        if readonly:
            return value
        link = cls()
        link.creator = account
        link.dataset = dataset
        link.value = value
        link.is_matched = value is not None
        link.key = data['key']
        db.session.add(link)
        db.session.flush()
        return link

    def match(self, dataset, data, account):
        state = LinkMatchState(dataset)
        data = LinkMatchSchema().to_python(data, state)
        self.is_matched = True
        self.matcher = account
        if data['choice'] == 'INVALID':
            self.value = None
            self.is_invalid = True
        elif data['choice'] == 'NEW':
            self.value = Value.create(dataset, data)
            self.is_invalid = False
        else:
            self.value = data['choice']
            self.is_invalid = False
        db.session.add(self)
        db.session.flush()

