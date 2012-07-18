# shut up useless SA warning:
import warnings; 
warnings.filterwarnings('ignore', 'Unicode type received non-unicode bind param value.')
from sqlalchemy.exc import SAWarning
warnings.filterwarnings('ignore', category=SAWarning)
import logging

from flask import Flask
from flask.ext.sqlalchemy import SQLAlchemy
from flaskext.oauth import OAuth

from nomenklatura import default_settings

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(default_settings)
app.config.from_envvar('NOMENKLATURA_SETTINGS', silent=True)

db = SQLAlchemy(app)

oauth = OAuth()
github = oauth.remote_app('github',
        base_url='http://github.com/login/oauth/',
        authorize_url='http://github.com/login/oauth/authorize',
        request_token_url=None,
        access_token_url='http://github.com/login/oauth/access_token',
        consumer_key=app.config.get('GITHUB_CLIENT_ID'),
        consumer_secret=app.config.get('GITHUB_CLIENT_SECRET'))



