from flask import render_template, Response, request
from flask import url_for, session, redirect

import requests
from formencode import Invalid

from linkspotting.core import app, db, github
from linkspotting.model import Dataset
from linkspotting.util import jsonify, response_format
from linkspotting.views.dataset import section as dataset
from linkspotting.views.value import section as value
from linkspotting.views.link import section as link

@app.context_processor
def set_template_globals():
    return {
        'datasets': Dataset.all(),
        'logged_in': 'login' in session,
        'login': session.get('login')
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
    session.clear()
    return redirect(url_for('index'))

@app.route('/gh/callback')
@github.authorized_handler
def authorized(resp):
    access_token = resp['access_token']
    session['access_token'] = access_token, ''
    res = requests.get('https://api.github.com/user?access_token=%s' % access_token)
    for k, v in res.json.items():
        session[k] = v
    return redirect(url_for('index'))

@app.route('/')
def index():
    return render_template('index.html')
