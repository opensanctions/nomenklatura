from normality import normalize
from flask.ext.script import Manager
from flask.ext.assets import ManageAssets

from nomenklatura.core import db
from nomenklatura.model import Entity
from nomenklatura.views import app
from nomenklatura.assets import assets

manager = Manager(app)
manager.add_command('assets', ManageAssets(assets))


@manager.command
def createdb():
    """ Make the database. """
    db.create_all()


@manager.command
def flush(dataset):
    ds = Dataset.by_name(dataset)
    for alias in Alias.all_unmatched(ds):
        db.session.delete(alias)
    db.session.commit()


if __name__ == '__main__':
    manager.run()
