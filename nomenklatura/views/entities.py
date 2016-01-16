from flask import Blueprint, request, url_for, redirect
from apikit import jsonify, Pager, arg_bool, request_data, obj_or_404

from nomenklatura.core import db
from nomenklatura.views.common import csvify, dataset_filename
from nomenklatura import authz
from nomenklatura.model import Entity, Dataset

section = Blueprint('entities', __name__)


@section.route('/entities', methods=['GET'])
def index():
    entities = Entity.all()
    dataset_arg = request.args.get('dataset')
    if dataset_arg is not None:
        dataset = Dataset.find(dataset_arg)
        entities = entities.filter_by(dataset=dataset)
    filter_name = request.args.get('filter_name', '')
    if len(filter_name):
        query = '%' + filter_name + '%'
        entities = entities.filter(Entity.name.ilike(query))

    # TODO, other filters.
    format = request.args.get('format', 'json').lower().strip()
    if format == 'csv':
        res = csvify(entities)
    else:
        pager = Pager(entities)
        res = jsonify(pager.to_dict())

    if arg_bool('download'):
        fn = dataset_filename(dataset, format)
        res.headers['Content-Disposition'] = 'attachment; filename=' + fn
    return res


@section.route('/entities', methods=['POST'])
def create():
    data = request_data()
    dataset = Dataset.from_form(data)
    authz.require(authz.dataset_edit(dataset))
    entity = Entity.create(dataset, data, request.account)
    db.session.commit()
    return redirect(url_for('.view', id=entity.id))


@section.route('/entities/<int:id>', methods=['GET'])
def view(id):
    entity = obj_or_404(Entity.by_id(id))
    return jsonify(entity)


@section.route('/datasets/<dataset>/find', methods=['GET'])
def by_name(dataset):
    dataset = Dataset.find(dataset)
    name = request.args.get('name')
    entity = obj_or_404(Entity.by_name(dataset, name))
    return jsonify(entity)


@section.route('/entities/<int:id>/aliases', methods=['GET'])
def aliases(id):
    entity = Entity.by_id(id)
    pager = Pager(entity.aliases, id=id)
    return jsonify(pager.to_dict())


@section.route('/entities/<id>', methods=['POST'])
def update(id):
    entity = Entity.by_id(id)
    authz.require(authz.dataset_edit(entity.dataset))
    entity.update(request_data(), request.account)
    db.session.commit()
    return redirect(url_for('.view', id=entity.id))
