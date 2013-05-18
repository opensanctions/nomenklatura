from datetime import datetime

from formencode import Schema, Invalid, validators

from nomenklatura.core import db
from nomenklatura.model.common import Name, FancyValidator
from nomenklatura.model.common import JsonType, DataBlob
from nomenklatura.model.entity import Entity
from nomenklatura.matching import match as match_op
from nomenklatura.util import flush_cache, add_candidate_to_cache


class AliasMatchState():

    def __init__(self, dataset):
        self.dataset = dataset

class ValidChoice(FancyValidator):

    def _to_python(self, value, state):
        if value == 'NEW':
            return value
        elif value == 'INVALID' and state.dataset.enable_invalid:
            return value
        entity = Entity.by_id(state.dataset, value)
        if entity is not None:
            return entity
        raise Invalid('No such entity.', value, None)

class AliasLookupSchema(Schema):
    allow_extra_fields = True
    name = validators.String(min=0, max=5000)
    data = DataBlob(if_missing={}, if_empty={})

class AliasMatchSchema(Schema):
    allow_extra_fields = True
    entity = validators.String(min=0, max=5000, if_missing='', if_empty='')
    choice = ValidChoice()

class Alias(db.Model):
    __tablename__ = 'alias'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    data = db.Column(JsonType, default=dict)
    is_matched = db.Column(db.Boolean, default=False)
    is_invalid = db.Column(db.Boolean, default=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey('dataset.id'))
    creator_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    matcher_id = db.Column(db.Integer, db.ForeignKey('account.id'),
            nullable=True)
    entity_id = db.Column(db.Integer, db.ForeignKey('entity.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    def as_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'entity': self.entity.as_dict(shallow=True) if self.entity else None,
            'created_at': self.created_at,
            'creator': self.creator.as_dict(),
            'updated_at': self.updated_at,
            'is_matched': self.is_matched,
            'data': self.data,
            'matcher': self.matcher.as_dict() if self.matcher else None,
            'is_invalid': self.is_invalid,
            'dataset': self.dataset.name
            }

    def as_row(self):
        if self.is_invalid:
            return None
        row = self.entity.as_row() if self.entity else {'name': None, 'id': None}
        for k, v in self.data.items():
            if k not in row:
                row[k] = v
        row['alias'] = self.name
        row['alias_id'] = self.id
        return row

    @property
    def display_name(self):
        return self.name

    @classmethod
    def by_name(cls, dataset, name):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(name=name).first()

    @classmethod
    def by_id(cls, dataset, id):
        return cls.query.filter_by(dataset=dataset).\
                filter_by(id=id).first()

    @classmethod
    def all(cls, dataset, eager=False):
        q = cls.query.filter_by(dataset=dataset)
        if eager:
            q = q.options(db.joinedload('matcher'))
            q = q.options(db.joinedload('creator'))
            q = q.options(db.joinedload('entity'))
            q = q.options(db.joinedload('dataset'))
        return q

    @classmethod
    def all_matched(cls, dataset):
        return cls.all(dataset).\
                filter_by(is_matched=True)

    @classmethod
    def all_unmatched(cls, dataset):
        return cls.all(dataset).\
                filter_by(is_matched=False)

    @classmethod
    def all_invalid(cls, dataset):
        return cls.all(dataset).\
                filter_by(is_invalid=True)

    @classmethod
    def find(cls, dataset, id):
        link = cls.by_id(dataset, id)
        if link is None:
            raise NotFound("No such link ID: %s" % id)
        return link

    @classmethod
    def lookup(cls, dataset, data, account, match_entity=True,
            readonly=False):
        data = AliasLookupSchema().to_python(data)
        if match_entity:
            entity = Entity.by_name(dataset, data['name'])
            if entity is not None:
                return entity
        else:
            entity = None
        alias = cls.by_name(dataset, data['name'])
        if alias is not None:
            return alias
        choices = match_op(data['name'], dataset)
        choices = filter(lambda (c,v,s): s > 99.9, choices)
        if len(choices)==1:
            c, entity_id, s = choices.pop()
            entity = Entity.by_id(dataset, entity_id)
        if readonly:
            return entity
        alias = cls()
        alias.creator = account
        alias.dataset = dataset
        alias.entity = entity
        alias.is_matched = entity is not None
        alias.name = data['name']
        alias.data = data['data']
        db.session.add(alias)
        db.session.flush()
        if entity is not None:
            add_candidate_to_cache(dataset, alias.name, entity.id)
        return alias

    def match(self, dataset, data, account):
        state = AliasMatchState(dataset)
        data = AliasMatchSchema().to_python(data, state)
        self.is_matched = True
        self.matcher = account
        if data['choice'] == 'INVALID':
            self.entity = None
            self.is_invalid = True
        elif data['choice'] == 'NEW':
            self.entity = Entity.create(dataset, data, account)
            self.is_invalid = False
        else:
            self.entity = data['choice']
            self.is_invalid = False
        db.session.add(self)
        db.session.flush()

