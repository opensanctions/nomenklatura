from flask import Blueprint, request, url_for
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

@section.route('/datasets', methods=['POST'])
def create():
    data = request_content()
    try:
        dataset = Dataset.create(data)
        redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return handle_invalid(inv, new, data=data)

@section.route('/<dataset>', methods=['GET'])
@section.route('/datasets/<dataset>', methods=['GET'])
def view(dataset):
    dataset = Dataset.find(dataset)
    return dataset.label


