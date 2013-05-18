from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.util import jsonify, csvify, csv_filename, Pager
from nomenklatura import authz
from nomenklatura.exc import NotFound
from nomenklatura.views.dataset import view as view_dataset
from nomenklatura.views.common import handle_invalid
from nomenklatura.matching import match as match_op
from nomenklatura.model import Dataset, Entity

section = Blueprint('entity', __name__)


@section.route('/<dataset>/entities.<format>', methods=['GET'])
@section.route('/<dataset>/entities', methods=['GET'])
def index(dataset, format='json'):
    dataset = Dataset.find(dataset)
    q = Entity.all(dataset, eager=True)
    if format == 'csv':
        fn = csv_filename(dataset, 'entities')
        headers = {
            'Content-Disposition': 'attachment; filename=' + fn
        }
        return csvify(q, headers=headers)
    return jsonify(q)


@section.route('/<dataset>/entities', methods=['POST'])
def create(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = request_content()
    try:
        entity = Entity.create(dataset, data, request.account)
        db.session.commit()
        return redirect(url_for('.view',
            dataset=dataset.name,
            entity=entity.id))
    except Invalid, inv:
        return handle_invalid(inv, view_dataset, data=data, 
                              args=[dataset.name])

@section.route('/<dataset>/entities/<entity>', methods=['GET'])
def view(dataset, entity):
    dataset = Dataset.find(dataset)
    entity = Entity.find(dataset, entity)
    print entity.data
    format = response_format()
    if format == 'json':
        return jsonify(entity)
    query = request.args.get('query', '').strip().lower()
    choices = match_op(entity.name, dataset)
    choices = filter(lambda (c,e,s): e != entity.id, choices)
    if len(query):
        choices = filter(lambda (c,e,s): query in Entity.find(dataset,e).name.lower(),
                         choices)
                         # THIS is very inefficient - rather do this
                         # differently
    pager = Pager(choices, '.view', dataset=dataset.name,
                  entity=entity.id, limit=10)

    # HACK: Fetch only the entities on the selected page.
    entities = Entity.id_map(dataset, map(lambda (c,v,s): v,
        pager.query[pager.offset:pager.offset+pager.limit]))
    for i, (c,e,s) in enumerate(pager.query):
        if e in entities:
            pager.query[i] = (c, entities.get(e), s)

    return render_template('entity/view.html', dataset=dataset,
                           entity=entity, entities=pager, query=query)

@section.route('/<dataset>/entities', methods=['GET'])
def view_by_name(dataset):
    dataset = Dataset.find(dataset)
    entity = Entity.by_name(dataset, request.args.get('name'))
    if entity is None:
        raise NotFound("No such entity: %s" % request.args.get('name'))
    return view(dataset.name, entity.id)

@section.route('/<dataset>/entities/<entity>', methods=['POST'])
def update(dataset, entity):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    entity = Entity.find(dataset, entity)
    data = request_content()
    try:
        entity.update(data, request.account)
        db.session.commit()
        flash("Updated %s" % entity.display_name, 'success')
        return redirect(url_for('.view', dataset=dataset.name, entity=entity.id))
    except Invalid, inv:
        return handle_invalid(inv, view, data=data,
                              args=[dataset.name, entity.id])

@section.route('/<dataset>/entities/<entity>/merge', methods=['POST'])
def merge(dataset, entity):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    entity = Entity.find(dataset, entity)
    data = request_content()
    try:
        target = entity.merge_into(data, request.account)
        db.session.commit()
        flash("Merged %s" % entity.display_name, 'success')
        return redirect(url_for('.view', dataset=dataset.name,
                        entity=target.id))
    except Invalid, inv:
        return handle_invalid(inv, view, data=data,
                              args=[dataset.name, entity.id])

