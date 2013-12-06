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
        err = {'file': "You need to upload a file"}
        raise Invalid("No file.", None, None, error_dict=err)
    upload = Upload.create(dataset, request.account, file_)
    db.session.commit()
    return jsonify(upload)


@section.route('/datasets/<dataset>/uploads/<id>', methods=['GET'])
def view(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    upload = Upload.find(dataset, id)
    return jsonify(upload)


@section.route('/datasets/<dataset>/uploads/<id>', methods=['POST'])
def process(dataset, id):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    upload = Upload.find(dataset, id)
    mapping = request_data()
    mapping['reviewed'] = mapping.get('reviewed') or False
    mapping['columns'] = mapping.get('columns', {})
    fields = mapping['columns'].values()
    for header in mapping['columns'].keys():
        if header not in upload.tab.headers:
            raise Invalid("Invalid header: %s" % header, None, None)    

    if 'name' not in fields and 'id' not in fields:
        raise Invalid("You have not selected a field that definies entity names.", None, None)

    import_upload.delay(upload.id, request.account.id, mapping)
    return jsonify({'status': 'Loading data...'})
