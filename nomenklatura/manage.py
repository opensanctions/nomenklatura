from flaskext.script import Manager

from nomenklatura.core import app, db
from nomenklatura.model import *
from nomenklatura import web

manager = Manager(app)

@manager.command
def createdb():
    """ Make the database. """
    db.create_all()

@manager.command
def cleanup():
    """ Clean up the database. """
    for dataset in Dataset.all():
        for link in Link.all_unmatched(dataset):
            db.session.delete(link)
        db.session.flush()
    db.session.commit()

if __name__ == '__main__':
    manager.run()
