from flask import Blueprint, request, url_for, flash
from formencode import Invalid
from flask.ext.utils.serialization import jsonify

from nomenklatura.views.common import request_data
from nomenklatura import authz
from nomenklatura.core import db
from nomenklatura.model import Dataset, Upload
from nomenklatura.importer import import_upload

section = Blueprint('upload', __name__)


@section.route('/datasets/<dataset>/uploads', methods=['POST'])
def upload(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    file_ = request.files.get('file')
    if not file_ or not file_.filename:
        inv = Invalid("No file.", None, None,
                      error_dict={'file': "You need to upload a file"})
        raise inv
    upload = Upload.create(dataset, request.account, file_)
    db.session.commit()
    return jsonify(upload)


@section.route('/datasets/<dataset>/uploads/<id>', methods=['GET'])
def view(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    upload = Upload.find(id)
    return jsonify(upload)


@section.route('/datasets/<dataset>/uploads/<id>', methods=['POST'])
def process(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    data = request_data()
    entity_col = data.get('entity') or None
    alias_col = data.get('alias') or None
    if not (entity_col or alias_col):
        flash('You need to pick either a alias or entity column!', 'error')
        return map(dataset.name, id)
    import_upload.delay(dataset.name, id, request.account.id,
                        entity_col, alias_col)
    flash('Loading data...', 'success')
    return redirect(url_for('dataset.view', dataset=dataset.name))
