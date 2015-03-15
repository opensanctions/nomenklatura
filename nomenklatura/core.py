import logging

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.oauth import OAuth
from flask.ext.assets import Environment

import certifi
from celery import Celery

from nomenklatura import default_settings

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('NOMENKLATURA_SETTINGS', silent=True)

db = SQLAlchemy(app)
assets = Environment(app)

celery = Celery('nomenklatura', broker=app.config['CELERY_BROKER_URL'])

oauth = OAuth()
github = oauth.remote_app('github',
        base_url='https://github.com/login/oauth/',
        authorize_url='https://github.com/login/oauth/authorize',
        request_token_url=None,
        access_token_url='https://github.com/login/oauth/access_token',
        consumer_key=app.config.get('GITHUB_CLIENT_ID'),
        consumer_secret=app.config.get('GITHUB_CLIENT_SECRET'))

github._client.ca_certs = certifi.where()
