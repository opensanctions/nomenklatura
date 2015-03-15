import os

#DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY')
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL',
                            os.environ.get('SHARED_DATABASE_URL'))

GITHUB_CLIENT_ID = os.environ.get('GITHUB_CLIENT_ID')
GITHUB_CLIENT_SECRET = os.environ.get('GITHUB_CLIENT_SECRET')

MEMCACHE_HOST = os.environ.get('MEMCACHIER_SERVERS')

S3_BUCKET = os.environ.get('S3_BUCKET', 'nomenklatura')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')

CELERY_BROKER = os.environ.get('CLOUDAMQP_URL')
