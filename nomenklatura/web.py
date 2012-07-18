from flask import render_template, Response, request
from flask import url_for, session, redirect, flash

import requests
from formencode import Invalid

from linkspotting.core import app, db, github
from linkspotting.model import Dataset, Account
from linkspotting.exc import Unauthorized
from linkspotting import authz
from linkspotting.util import jsonify, response_format
from linkspotting.views.dataset import section as dataset
from linkspotting.views.value import section as value
from linkspotting.views.link import section as link

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
    """ Re-format exceptions to JSON if accept requires that. """
    format = response_format()
    if format == 'json':
        body = {'status': exc.code,
                'name': exc.name,
                'message': exc.get_description(request.environ)}
        return jsonify(body, status=exc.code,
                       headers=exc.get_headers(request.environ))
    return exc

app.register_blueprint(dataset)
app.register_blueprint(value)
app.register_blueprint(link)

@app.route('/gh/login')
def login():
    callback=url_for('authorized', _external=True)
    return github.authorize(callback=callback)

@app.route('/gh/logout')
def logout():
    authz.require(authz.logged_in())
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for('index'))

@app.route('/gh/callback')
@github.authorized_handler
def authorized(resp):
    if not 'access_token' in resp:
        return redirect(url_for('index'))
    access_token = resp['access_token']
    session['access_token'] = access_token, ''
    res = requests.get('https://api.github.com/user?access_token=%s' % access_token)
    for k, v in res.json.items():
        session[k] = v
    account = Account.by_github_id(res.json.get('id'))
    if account is None:
        account = Account.create(res.json)
        db.session.commit()
    flash("Welcome back, %s." % account.login, "success")
    return redirect(url_for('index'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/account')
def account():
    authz.require(authz.logged_in())
    return render_template('account.html', 
            api_key=request.account.api_key)

@app.route('/')
def index():
    datasets = Dataset.all()
    return render_template('index.html', datasets=datasets)
