DEBUG = True
SECRET_KEY = 'no'
SQLALCHEMY_DATABASE_URI = 'sqlite:///master.sqlite3'
CELERY_BROKER_URL = 'amqp://guest:guest@localhost:5672//'

GITHUB_CLIENT_ID = '6f376bedb69c3a0d3a24'
GITHUB_CLIENT_SECRET = '1c8588ce799541c0a28e2d6a73f2128090ea463c'

ALLOWED_EXTENSIONS = set(['csv', 'tsv', 'ods', 'xls', 'xlsx', 'txt'])
