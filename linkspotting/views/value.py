from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid

from linkspotting.core import db
from linkspotting.util import request_content
from linkspotting.views.dataset import view as view_dataset
from linkspotting.views.common import handle_invalid
from linkspotting.model import Dataset, Value

section = Blueprint('value', __name__)

@section.route('/<dataset>/values', methods=['POST'])
def create(dataset):
    dataset = Dataset.find(dataset)
    data = request_content()
    try:
        value = Value.create(dataset, data)
        db.session.commit()
        return redirect(url_for('.view',
            dataset=dataset.name,
            value=value.id))
    except Invalid, inv:
        return handle_invalid(inv, view_dataset, data=data, 
                              args=[dataset.name])

@section.route('/<dataset>/values/<value>', methods=['GET'])
def view(dataset, value):
    dataset = Dataset.find(dataset)
    value = Value.find(dataset, value)
    return render_template('value/view.html', dataset=dataset,
                           value=value)

@section.route('/<dataset>/values/<value>', methods=['POST'])
def update(dataset, value):
    dataset = Dataset.find(dataset)
    value = Value.find(dataset, value)
    data = request_content()
    try:
        value.update(data)
        db.session.commit()
        flash("Updated %s" % value.value, 'success')
        return redirect(url_for('.view', dataset=dataset.name, value=value.id))
    except Invalid, inv:
        return handle_invalid(inv, view, data=data,
                              args=[dataset.name, value.id])

