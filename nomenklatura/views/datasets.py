from flask import Blueprint, request, url_for
from flask import redirect
from apikit import jsonify, Pager

from nomenklatura.core import db
from nomenklatura.views.common import request_data
from nomenklatura.views.pager import query_pager
from nomenklatura import authz
from nomenklatura.model import Dataset
from nomenklatura.model.matching import attribute_keys

section = Blueprint('datasets', __name__)


@section.route('/datasets', methods=['GET'])
def index():
    datasets = Dataset.all()
    pager = Pager(datasets)
    return jsonify(pager.to_dict())


@section.route('/datasets', methods=['POST'])
def create():
    authz.require(authz.dataset_create())
    dataset = Dataset.create(request_data(), request.account)
    db.session.commit()
    return redirect(url_for('.view', dataset=dataset.name))


@section.route('/datasets/<dataset>', methods=['GET'])
def view(dataset):
    dataset = Dataset.find(dataset)
    return jsonify(dataset)


@section.route('/datasets/<dataset>/attributes', methods=['GET'])
def attributes(dataset):
    dataset = Dataset.find(dataset)
    return jsonify({'attributes': attribute_keys(dataset)})


@section.route('/datasets/<dataset>', methods=['POST'])
def update(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_manage(dataset))
    dataset.update(request_data())
    db.session.commit()
    return redirect(url_for('.view', dataset=dataset.name))
