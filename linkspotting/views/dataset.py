from flask import Blueprint, request, url_for
from flask import render_template, redirect
from formencode import Invalid, htmlfill

from linkspotting.core import db
from linkspotting.util import request_content
from linkspotting.model import Dataset

section = Blueprint('dataset', __name__)

@section.route('/new', methods=['GET'])
def new():
    return render_template('dataset/new.html')

@section.route('/new', methods=['POST'])
def create():
    data = request_content()
    try:
        dataset = Dataset.create(data)
        redirect(url_for('.view', dataset=dataset.name))
    except Invalid, inv:
        return htmlfill.render(new(), defaults=data,
                               errors=inv.unpack_errors())

@section.route('/<dataset>', methods=['GET'])
def view(dataset):
    return dataset
