import logging

from flask import Flask
from flask import url_for as _url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.oauth import OAuth
from flask.ext.assets import Environment

from nomenklatura import default_settings

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('NOMENKLATURA_SETTINGS', silent=True)
app_name = app.config.get('APP_NAME')

db = SQLAlchemy(app)
assets = Environment(app)

oauth = OAuth()
github = oauth.remote_app('github',
        base_url='https://github.com/login/oauth/',
        authorize_url='https://github.com/login/oauth/authorize',
        request_token_url=None,
        access_token_url='https://github.com/login/oauth/access_token',
        consumer_key=app.config.get('GITHUB_CLIENT_ID'),
        consumer_secret=app.config.get('GITHUB_CLIENT_SECRET'))


def url_for(*a, **kw):
    try:
        kw['_external'] = True
        return _url_for(*a, **kw)
    except RuntimeError:
        return None
