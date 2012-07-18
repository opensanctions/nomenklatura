from flaskext.script import Manager

from nomenklatura.core import app, db
from nomenklatura.model import *
from nomenklatura import web

manager = Manager(app)

@manager.command
def createdb():
    """ Make the database. """
    db.create_all()

if __name__ == '__main__':
    manager.run()
