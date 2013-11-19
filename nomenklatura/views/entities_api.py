from flask import Blueprint, request, url_for
from flask import redirect

from nomenklatura.core import db
from nomenklatura.util import request_content
from nomenklatura.util import jsonify
from nomenklatura.views.pager import query_pager
from nomenklatura import authz
from nomenklatura.model import Entity, Dataset

section = Blueprint('entities', __name__)


@section.route('/entities', methods=['GET'])
def index():
    entities = Entity.all()
    dataset_arg = request.args.get('dataset')
    if dataset_arg is not None:
        dataset = Dataset.find(dataset_arg)
        entities = entities.filter_by(dataset=dataset)
    filter_name = request.args.get('filter_name', '')
    if len(filter_name):
        query = '%' + filter_name + '%'
        entities = entities.filter(Entity.name.ilike(query))
    # TODO, other filters.
    # TODO, format & download flags
    return query_pager(entities)
