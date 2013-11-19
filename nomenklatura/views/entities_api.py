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
    # TODO, other filters.
    # TODO, format & download flags
    return query_pager(entities)
