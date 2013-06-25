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
    return render_template('upload/form.html', dataset=dataset)


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
    upload = upload_file(dataset, file_, request.account)
    return redirect(url_for('.map', dataset=dataset.name, id=upload.id))


@section.route('/<dataset>/upload/<id>', methods=['GET'])
def map(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = get_map_metadata(dataset, id)
    return render_template('upload/map.html', **data)


@section.route('/<dataset>/upload/<id>', methods=['POST'])
def submit(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = request_content()
    entity_col = data.get('entity') or None
    alias_col = data.get('alias') or None
    if not (entity_col or alias_col):
        flash('You need to pick either a alias or entity column!', 'error')
        return map(dataset.name, id)
    import_upload.delay(dataset.name, id, request.account.id,
                        entity_col, alias_col)
    flash('Loading data...', 'success')
    return redirect(url_for('dataset.view', dataset=dataset.name))
