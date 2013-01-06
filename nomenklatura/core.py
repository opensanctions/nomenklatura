# shut up useless SA warning:
import warnings; 
warnings.filterwarnings('ignore', 'Unicode type received non-unicode bind param value.')
from sqlalchemy.exc import SAWarning
warnings.filterwarnings('ignore', category=SAWarning)

import os
import logging

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flaskext.oauth import OAuth
import certifi
from pylibmc import Client as MemcacheClient
from boto.s3.connection import S3Connection
from celery import Celery

from nomenklatura import default_settings

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('NOMENKLATURA_SETTINGS', silent=True)

db = SQLAlchemy(app)
s3 = S3Connection(app.config['S3_ACCESS_KEY'], app.config['S3_SECRET_KEY'])
celery = Celery('nomenklatura', broker=app.config['CELERY_BROKER'])

oauth = OAuth()
github = oauth.remote_app('github',
        base_url='https://github.com/login/oauth/',
        authorize_url='https://github.com/login/oauth/authorize',
        request_token_url=None,
        access_token_url='https://github.com/login/oauth/access_token',
        consumer_key=app.config.get('GITHUB_CLIENT_ID'),
        consumer_secret=app.config.get('GITHUB_CLIENT_SECRET'))

github._client.ca_certs = certifi.where()
#if 'MEMCACHE_USERNAME' in os.environ:
memcache = MemcacheClient(
    servers=[app.config.get('MEMCACHE_HOST', '127.0.0.1:11211')],
    username=os.environ.get('MEMCACHIER_USERNAME'),
    password=os.environ.get('MEMCACHIER_PASSWORD'),
    binary=True
    )
#try:
#    memcache.flush_all()
#except: pass
