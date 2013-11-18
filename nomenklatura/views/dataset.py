from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect, Response
from werkzeug.http import http_date
from formencode import Invalid, htmlfill

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.util import jsonify, Pager
from nomenklatura import authz
from nomenklatura.views.common import handle_invalid
from nomenklatura.model import Dataset, Alias, Entity
from nomenklatura.matching import get_algorithms

section = Blueprint('dataset', __name__)

@section.route('/new', methods=['GET'])
def new():
    authz.require(authz.dataset_create())
    return render_template('dataset/new.html')

@section.route('/datasets', methods=['GET'])
def index():
    format = response_format()
    if format == 'json':
        return jsonify(Dataset.all())
    return "Not implemented!"

@section.route('/', methods=['POST'])
def create():
    authz.require(authz.dataset_create())
    data = request_content()
    try:
        dataset = Dataset.create(data, request.account)
        db.session.commit()
        return redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return handle_invalid(inv, new, data=data)

@section.route('/<dataset>', methods=['GET'])
def view(dataset):
    dataset = Dataset.find(dataset)
    format = response_format()
    headers = {
        'X-Dataset': dataset.name,
        'Last-Modified': http_date(dataset.last_modified)
    }
    if format == 'json':
        return jsonify(dataset, headers=headers)
    unmatched = Alias.all_unmatched(dataset).count()
    entities = Entity.all(dataset, query=request.args.get('query'))
    pager = Pager(entities, '.view', dataset=dataset.name,
                  limit=10)
    html = render_template('dataset/view.html',
            entities=pager,
            num_entities=len(pager),
            num_aliases=Alias.all(dataset).count(),
            invalid=Alias.all_invalid(dataset).count(),
            query=request.args.get('query', ''),
            dataset=dataset, unmatched=unmatched)
    return Response(html, headers=headers)

@section.route('/<dataset>/edit', methods=['GET'])
def edit(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_manage(dataset))
    html = render_template('dataset/edit.html',
                           dataset=dataset,
                           algorithms=get_algorithms())
    return htmlfill.render(html, defaults=dataset.as_dict())

@section.route('/<dataset>', methods=['POST'])
def update(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_manage(dataset))
    data = request_content()
    try:
        dataset.update(data)
        db.session.commit()
        flash("Updated %s" % dataset.label, 'success')
        return redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return handle_invalid(inv, edit, 
                args=[dataset.name], data=data)


