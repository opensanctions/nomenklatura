import requests
from flask import url_for, session, Blueprint, redirect
from flask import flash

from nomenklatura import authz
from nomenklatura.core import db, github
from nomenklatura.model import Account

section = Blueprint('sessions', __name__)


@section.route('/gh/login')
def login():
    callback=url_for('sessions.authorized', _external=True)
    return github.authorize(callback=callback)


@section.route('/gh/logout')
def logout():
    authz.require(authz.logged_in())
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for('index'))


@section.route('/gh/callback')
@github.authorized_handler
def authorized(resp):
    if not 'access_token' in resp:
        return redirect(url_for('index'))
    access_token = resp['access_token']
    session['access_token'] = access_token, ''
    res = requests.get('https://api.github.com/user?access_token=%s' % access_token,
            verify=False)
    data = res.json()
    for k, v in data.items():
        session[k] = v
    account = Account.by_github_id(data.get('id'))
    if account is None:
        account = Account.create(data)
        db.session.commit()
    flash("Welcome back, %s." % account.login, "success")
    return redirect(url_for('index'))
