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
def updb():
    """ Update the database. """
    db.engine.execute('ALTER TABLE "link" ADD COLUMN "data" TEXT')
    db.engine.execute("""UPDATE "link" SET "data" = '{}'""")
    db.session.commit()

@manager.command
def flush(dataset):
    ds = Dataset.by_name(dataset)
    for link in Link.all_unmatched(ds):
        db.session.delete(link)
    db.session.commit()

@manager.command
def dedup(dataset):
    ds = Dataset.by_name(dataset)
    from time import time
    from nomenklatura.matching import match
    begin = time()
    for value in Value.all(ds).limit(20):
        matches = match(value.value, ds)
        matches = filter(lambda (c,v,s): v!=value, matches)
        print [value.value, '=?', matches[0][1], matches[0][2]]
    print "Time: %.2fms" % ((time() - begin)*1000)

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

