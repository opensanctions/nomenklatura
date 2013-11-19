import urllib
import os

from flask import render_template, request
from flask import session, Markup
from formencode import Invalid
from flask.ext.utils.serialization import jsonify

from nomenklatura.core import app
from nomenklatura.model import Dataset, Account
from nomenklatura.exc import Unauthorized
from nomenklatura import authz
from nomenklatura.views.upload import section as upload
from nomenklatura.views.sessions import section as sessions
from nomenklatura.views.datasets import section as datasets
from nomenklatura.views.entities import section as entities
from nomenklatura.views.reconcile import section as reconcile


@app.before_request
def check_auth():
    api_key = request.headers.get('Authorization') \
              or request.args.get('api_key')
    if session.get('id'):
        request.account = Account.by_github_id(session.get('id'))
        if request.account is None:
            del session['id']
            raise Unauthorized()
    elif api_key is not None:
        request.account = Account.by_api_key(api_key)
        if request.account is None:
            raise Unauthorized()
    else: 
        request.account = None


@app.template_filter('urlencode')
def urlencode_filter(s):
    if type(s) == 'Markup':
        s = s.unescape()
    s = s.encode('utf8')
    s = urllib.quote_plus(s)
    return Markup(s)


@app.context_processor
def set_template_globals():
    return {
        'datasets': Dataset.all(),
        'authz': authz,
        'avatar_url': session.get('avatar_url', ''),
        'logged_in': request.account is not None,
        'login': request.account.login if request.account else None
        }


@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(410)
@app.errorhandler(500)
def handle_exceptions(exc):
    message = exc.get_description(request.environ)
    message = message.replace('<p>', '').replace('</p>', '')
    body = {
        'status': exc.code,
        'name': exc.name,
        'message': message
    }
    return jsonify(body, status=exc.code,
        headers=exc.get_headers(request.environ))


@app.errorhandler(Invalid)
def handle_invalid(exc):
    body = {
        'status': 400,
        'name': 'Invalid Data',
        'description': unicode(exc),
        'errors': exc.unpack_errors()
    }
    return jsonify(body, status=400)


app.register_blueprint(upload)
app.register_blueprint(reconcile)
app.register_blueprint(sessions, url_prefix='/api/2')
app.register_blueprint(datasets, url_prefix='/api/2')
app.register_blueprint(entities, url_prefix='/api/2')


def angular_templates():
    #if app.config.get('ASSETS_DEBUG'):
    #    return
    partials_dir = os.path.join(app.static_folder, 'templates')
    for (root, dirs, files) in os.walk(partials_dir):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            with open(file_path, 'rb') as fh:
                yield ('/static/templates/%s' % file_path[len(partials_dir)+1:],
                       fh.read().decode('utf-8'))


@app.route('/')
def index():
    return render_template('app.html', angular_templates=angular_templates())
