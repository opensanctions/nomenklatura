from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid

from linkspotting.core import db
from linkspotting.util import request_content
from linkspotting.views.common import handle_invalid
from linkspotting.model import Dataset

section = Blueprint('dataset', __name__)

@section.route('/new', methods=['GET'])
def new():
    return render_template('dataset/new.html')

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
    return render_template('dataset/view.html', dataset=dataset)

@section.route('/<dataset>/edit', methods=['GET'])
def edit(dataset):
    dataset = Dataset.find(dataset)
    return render_template('dataset/edit.html',
                           dataset=dataset)

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
        return handle_invalid(inv, edit, dataset.name, data=data)


