DEBUG = True
SECRET_KEY = 'no'
SQLALCHEMY_DATABASE_URI = 'sqlite:///master.sqlite3'

GITHUB_CLIENT_ID = 'da79a6b5868e690ab984'
GITHUB_CLIENT_SECRET = '1701d3bd20bbb29012592fd3a9c64b827e0682d6'

CELERY_BROKER = 'amqp://guest@localhost//'

ALLOWED_EXTENSIONS = set(['csv', 'tsv', 'ods', 'xls', 'xlsx', 'txt'])

