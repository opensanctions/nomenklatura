from random import randint

from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect, Response
from formencode import Invalid, htmlfill

from linkspotting.core import db
from linkspotting.util import request_content, response_format
from linkspotting.util import jsonify
from linkspotting.exc import NotFound
from linkspotting.views.common import handle_invalid
from linkspotting.model import Dataset, Value, Link
from linkspotting.matching import match as match_op

section = Blueprint('link', __name__)

@section.route('/<dataset>/links', methods=['GET'])
def index(dataset):
    dataset = Dataset.find(dataset)
    format = response_format()
    if format == 'json':
        return jsonify(Link.all(dataset))
    return "Not implemented!"

@section.route('/<dataset>/links/<link>', methods=['GET'])
def view(dataset, link):
    dataset = Dataset.find(dataset)
    link = Link.find(dataset, link)
    format = response_format()
    if format == 'json':
        return jsonify(link)
    return "Not implemented!"

@section.route('/<dataset>/lookup', methods=['POST', 'GET'])
def lookup(dataset):
    dataset = Dataset.find(dataset)
    data = request_content()
    format = response_format()
    try:
        link = Link.lookup(dataset, data)
        if link is None:
            if format == 'json':
                return jsonify({
                    'is_matched': False,
                    'value': None,
                    'key': data.get('key'),
                    'dataset': dataset.name
                    }, status=404)
            raise NotFound("No such link.")
        db.session.commit()
        status = 200 if link.is_matched else 404
        status = 418 if link.is_invalid else status
        if format == 'json':
            return jsonify(link, status=status)
        return Response(repr(link), status=status)
    except Invalid, inv:
        return handle_invalid(inv, index, data=data, 
                              args=[dataset.name])

@section.route('/<dataset>/match', methods=['GET'])
def match_random(dataset):
    dataset = Dataset.find(dataset)
    links = Link.all_unmatched(dataset)
    count = links.count()
    if count == 0:
        return redirect(url_for('dataset.view',
            dataset=dataset.name))
    link = links.offset(randint(0, count-1)).first()
    return match(dataset.name, link.id, random=True)

@section.route('/<dataset>/links/<link>/match', methods=['GET'])
def match(dataset, link, random=False):
    dataset = Dataset.find(dataset)
    link = Link.find(dataset, link)
    choices = match_op(link.key, dataset)
    html = render_template('link/match.html',
            dataset=dataset, link=link, choices=choices, 
            random=random)
    choice = 'INVALID' if link.is_invalid else link.value_id
    if len(choices):
        choice = choices[0][1].id if choice is None else choice
    return htmlfill.render(html,
            defaults={'choice': choice, 'value': link.key,
                      'random': random})

@section.route('/<dataset>/links/<link>/match', methods=['POST'])
def match_save(dataset, link):
    dataset = Dataset.find(dataset)
    link = Link.find(dataset, link)
    random = request.form.get('random')=='True'
    data = request_content()
    try:
        link.match(dataset, data)
        db.session.commit()
    except Invalid, inv:
        return handle_invalid(inv, match, data=data, 
                              args=[dataset.name, link.id, random])

    flash("Matched: %s" % link.key, "success")
    if random:
        return match_random(dataset.name)
    else:
        return match(dataset.name, link.id)

