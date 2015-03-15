from random import randint

from flask import Blueprint, request
from apikit import jsonify, Pager, arg_int

from nomenklatura.model.matching import find_matches
from nomenklatura.model import Dataset, Entity


section = Blueprint('matching', __name__)


@section.route('/match', methods=['GET'])
def match():
    dataset_arg = request.args.get('dataset')
    dataset = Dataset.find(dataset_arg)
    matches = find_matches(dataset,
                           request.args.get('name'),
                           filter=request.args.get('filter'),
                           exclude=arg_int('exclude'))
    pager = Pager(matches)
    return jsonify(pager.to_dict())


@section.route('/datasets/<dataset>/review', methods=['GET'])
def review(dataset):
    entities = Entity.all()
    dataset = Dataset.find(dataset)
    entities = entities.filter_by(dataset=dataset)
    entities = entities.filter(Entity.reviewed == False)  # noqa
    review_count = entities.count()
    if review_count == 0:
        return jsonify(None)
    entities = entities.offset(randint(0, review_count - 1))
    return jsonify(entities.first())
