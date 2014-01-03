DEBUG = True
SECRET_KEY = 'no'
SQLALCHEMY_DATABASE_URI = 'sqlite:///master.sqlite3'
CELERY_BROKER_URL = 'amqp://guest:guest@localhost:5672//'

GITHUB_CLIENT_ID = 'da79a6b5868e690ab984'
GITHUB_CLIENT_SECRET = '1701d3bd20bbb29012592fd3a9c64b827e0682d6'

ALLOWED_EXTENSIONS = set(['csv', 'tsv', 'ods', 'xls', 'xlsx', 'txt'])

