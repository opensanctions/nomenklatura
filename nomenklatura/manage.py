from flaskext.script import Manager

from linkspotting.core import app, db
from linkspotting.model import *
from linkspotting import web

manager = Manager(app)

@manager.command
def createdb():
    """ Make the database. """
    db.create_all()

if __name__ == '__main__':
    manager.run()
