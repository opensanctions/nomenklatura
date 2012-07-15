from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid, htmlfill

from linkspotting.core import db
from linkspotting.util import request_content, response_format
from linkspotting.util import jsonify
from linkspotting.views.common import handle_invalid
from linkspotting.model import Dataset, Link

section = Blueprint('dataset', __name__)

@section.route('/new', methods=['GET'])
def new():
    return render_template('dataset/new.html')

@section.route('/datasets', methods=['GET'])
def index():
    format = response_format()
    if format == 'json':
        return jsonify(Dataset.all())
    return "Not implemented!"

@section.route('/', methods=['POST'])
def create():
    data = request_content()
    try:
        dataset = Dataset.create(data)
        db.session.commit()
        return redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return handle_invalid(inv, new, data=data)

@section.route('/<dataset>', methods=['GET'])
def view(dataset):
    dataset = Dataset.find(dataset)
    format = response_format()
    if format == 'json':
        return jsonify(dataset)
    unmatched = Link.all_unmatched(dataset).count()
    return render_template('dataset/view.html', 
            dataset=dataset, unmatched=unmatched)

@section.route('/<dataset>/edit', methods=['GET'])
def edit(dataset):
    dataset = Dataset.find(dataset)
    html = render_template('dataset/edit.html',
                           dataset=dataset)
    return htmlfill.render(html, defaults=dataset.as_dict())

@section.route('/<dataset>', methods=['POST'])
def update(dataset):
    dataset = Dataset.find(dataset)
    data = request_content()
    try:
        dataset.update(data)
        db.session.commit()
        flash("Updated %s" % dataset.label, 'success')
        return redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return handle_invalid(inv, edit, 
                args=[dataset.name], data=data)


