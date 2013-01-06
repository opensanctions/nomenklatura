from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid, htmlfill

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.views.common import handle_invalid
from nomenklatura import authz
from nomenklatura.model import Dataset
from nomenklatura.importer import upload_file, get_map_metadata, \
    import_upload

section = Blueprint('upload', __name__)

@section.route('/<dataset>/upload', methods=['GET'])
def form(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    return render_template('upload/view.html', dataset=dataset)

@section.route('/<dataset>/upload', methods=['POST'])
def upload(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    file_ = request.files.get('file')
    if not file_ or not file_.filename:
        inv = Invalid("No file.", None, None,
                error_dict={'file': "You need to upload a file"})
        return handle_invalid(inv, form, data={},
                args=[dataset.name])
    sig = upload_file(dataset, file_)
    return redirect(url_for('.map', dataset=dataset.name, sig=sig))

@section.route('/<dataset>/upload/<sig>', methods=['GET'])
def map(dataset, sig):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = get_map_metadata(dataset, sig)
    return render_template('upload/map.html', **data)

@section.route('/<dataset>/upload/<sig>', methods=['POST'])
def submit(dataset, sig):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = request_content()
    value_col = data.get('value') or None
    link_col = data.get('link') or None
    if not (value_col or link_col):
        flash('You need to pick either a link or value column!', 'error')
        return map(dataset.name, sig)
    import_upload.delay(dataset.name, sig, request.account.id,
            value_col, link_col)
    flash('Loading data...', 'success')
    return redirect(url_for('dataset.view', dataset=dataset.name))

