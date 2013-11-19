from flask import Blueprint, request, url_for
from flask import redirect

from nomenklatura.core import db
from nomenklatura.util import request_content
from nomenklatura.util import jsonify
from nomenklatura.views.pager import query_pager
from nomenklatura import authz
from nomenklatura.model import Dataset

section = Blueprint('datasets', __name__)


@section.route('/datasets', methods=['GET'])
def index():
    datasets = Dataset.all()
    return query_pager(datasets)


@section.route('/datasets', methods=['POST'])
def create():
    authz.require(authz.dataset_create())
    data = request_content()
    dataset = Dataset.create(data, request.account)
    db.session.commit()
    return redirect(url_for('.view', dataset=dataset.name))


@section.route('/datasets/<dataset>', methods=['GET'])
def view(dataset):
    dataset = Dataset.find(dataset)
    return jsonify(dataset)


@section.route('/datasets/<dataset>', methods=['POST'])
def update(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_manage(dataset))
    data = request_content()
    dataset.update(data)
    db.session.commit()
    #flash("Updated %s" % dataset.label, 'success')
    return redirect(url_for('.view', dataset=dataset.name))
