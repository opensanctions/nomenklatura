from flask import Blueprint, request

from nomenklatura.views.pager import query_pager
#from nomenklatura import authz
from nomenklatura.model.matching import find_matches
from nomenklatura.model import Dataset

section = Blueprint('matching', __name__)


@section.route('/match', methods=['GET'])
def match():
    dataset_arg = request.args.get('dataset')
    exclude = request.args.get('exclude')
    dataset = Dataset.find(dataset_arg)
    matches = find_matches(dataset,
        request.args.get('name'),
        exclude=exclude)
    return query_pager(matches)
