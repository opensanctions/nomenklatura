from datetime import datetime

from formencode import Schema, All, Invalid, validators

from nomenklatura.core import db
from nomenklatura.model.common import Name, FancyValidator
from nomenklatura.exc import NotFound


class AvailableDatasetName(FancyValidator):

    def _to_python(self, value, state):
        if Dataset.by_name(value) is None:
            return value
        raise Invalid('Dataset already exists.', value, None)


class DatasetNewSchema(Schema):
    name = All(AvailableDatasetName(), Name(not_empty=True))
    label = validators.String(min=3, max=255)


class DatasetEditSchema(Schema):
    label = validators.String(min=3, max=255)
    match_aliases = validators.StringBool(if_missing=False)
    ignore_case = validators.StringBool(if_missing=False)
    public_edit = validators.StringBool(if_missing=False)
    normalize_text = validators.StringBool(if_missing=False)
    enable_invalid = validators.StringBool(if_missing=False)


class Dataset(db.Model):
    __tablename__ = 'dataset'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode)
    label = db.Column(db.Unicode)
    ignore_case = db.Column(db.Boolean, default=False)
    match_aliases = db.Column(db.Boolean, default=False)
    public_edit = db.Column(db.Boolean, default=False)
    normalize_text = db.Column(db.Boolean, default=True)
    enable_invalid = db.Column(db.Boolean, default=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('account.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
            onupdate=datetime.utcnow)

    entities = db.relationship('Entity', backref='dataset',
                             lazy='dynamic')
    aliases = db.relationship('Alias', backref='dataset',
                             lazy='dynamic')
    uploads = db.relationship('Upload', backref='dataset',
                               lazy='dynamic')

    def as_dict(self):
        from nomenklatura.model.alias import Alias
        from nomenklatura.model.entity import Entity
        num_aliases = Alias.all(self).count()
        num_unmatched = Alias.all_unmatched(self).count()
        num_entities = Entity.all(self).count()
        num_invalid = Alias.all_invalid(self).count()
    
        return {
            'id': self.id,
            'name': self.name,
            'label': self.label,
            'owner': self.owner.as_dict(),
            'stats': {
                'num_aliases': num_aliases,
                'num_entities': num_entities,
                'num_unmatched': num_unmatched,
                'num_invalid': num_invalid
            },
            'ignore_case': self.ignore_case,
            'match_aliases': self.match_aliases,
            'public_edit': self.public_edit,
            'normalize_text': self.normalize_text,
            'enable_invalid': self.enable_invalid,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    @property
    def last_modified(self):
        dates = [self.updated_at]
        from nomenklatura.model.entity import Entity
        latest_entity = self.entities.order_by(Entity.updated_at.desc()).first()
        if latest_entity is not None:
            dates.append(latest_entity.updated_at)

        from nomenklatura.model.alias import Alias
        latest_alias = self.aliases.order_by(Alias.updated_at.desc()).first()
        if latest_alias is not None:
            dates.append(latest_alias.updated_at)
        return max(dates)

    @classmethod
    def by_name(cls, name):
        return cls.query.filter_by(name=name).first()

    @classmethod
    def find(cls, name):
        dataset = cls.by_name(name)
        if dataset is None:
            raise NotFound("No such dataset: %s" % name)
        return dataset

    @classmethod
    def all(cls):
        return cls.query

    @classmethod
    def create(cls, data, account):
        data = DatasetNewSchema().to_python(data)
        dataset = cls()
        dataset.owner = account
        dataset.name = data['name']
        dataset.label = data['label']
        db.session.add(dataset)
        db.session.flush()
        return dataset

    def update(self, data):
        data = DatasetEditSchema().to_python(data)
        self.label = data['label']
        self.normalize_text = data['normalize_text']
        self.ignore_case = data['ignore_case']
        self.public_edit = data['public_edit']
        self.match_aliases = data['match_aliases']
        self.enable_invalid = data['enable_invalid']
        db.session.add(self)
        db.session.flush()

