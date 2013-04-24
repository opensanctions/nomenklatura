from random import randint

from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect, Response
from formencode import Invalid, htmlfill, validators

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.util import jsonify, Pager
from nomenklatura import authz
from nomenklatura.exc import NotFound
from nomenklatura.views.common import handle_invalid
from nomenklatura.model import Dataset, Value, Link
from nomenklatura.matching import match as match_op

section = Blueprint('link', __name__)

@section.route('/<dataset>/links', methods=['GET'])
def index(dataset):
    dataset = Dataset.find(dataset)
    format = response_format()
    if format == 'json':
        return jsonify(Link.all(dataset, eager=True))
    return "Not implemented!"

@section.route('/<dataset>/links/<link>', methods=['GET'])
def view(dataset, link):
    dataset = Dataset.find(dataset)
    link = Link.find(dataset, link)
    format = response_format()
    if format == 'json':
        return jsonify(link)
    return "Not implemented!"

@section.route('/<dataset>/link', methods=['GET'])
def view_by_name(dataset):
    dataset = Dataset.find(dataset)
    link = Link.by_name(dataset, request.args.get('name'))
    if link is None:
        raise NotFound("No such link: %s" % request.args.get('name'))
    return view(dataset.name, link.id)

@section.route('/<dataset>/lookup', methods=['POST', 'GET'])
def lookup(dataset):
    dataset = Dataset.find(dataset)
    readonly = validators.StringBool(if_empty=False, if_missing=False)\
            .to_python(request.args.get('readonly'))
    readonly = readonly if authz.logged_in() else True
    data = request_content()
    if response_format() != 'json':
        return Response("Not implemented!", status=400)

    try:
        link = Link.lookup(dataset, data, request.account,
                           readonly=readonly)
        if link is None:
            return jsonify({
                'is_matched': False,
                'value': None,
                'name': data.get('name'),
                'dataset': dataset.name
                }, status=404)

        if isinstance(link, Value):
            return jsonify({
                'is_matched': True,
                'value': link,
                'name': data.get('name'),
                'dataset': dataset.name
                }, status=200)

        db.session.commit()
        status = 200 if link.is_matched else 404
        status = 418 if link.is_invalid else status
        return jsonify(link, status=status)
    except Invalid, inv:
        return handle_invalid(inv, index, data=data,
                              args=[dataset.name])

@section.route('/<dataset>/match', methods=['GET'])
def match_random(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    links = Link.all_unmatched(dataset)
    count = links.count()
    if count == 0:
        return redirect(url_for('dataset.view',
            dataset=dataset.name))
    link = links.offset(randint(0, count-1)).first()
    return redirect(url_for('.match', dataset=dataset.name, link=link.id,
                            random=True))

@section.route('/<dataset>/links/<link>/match', methods=['GET'])
def match(dataset, link, random=False):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    link = Link.find(dataset, link)
    random = random or request.args.get('random')=='True'
    choices = match_op(link.name, dataset,
            query=request.args.get('query'))
    pager = Pager(choices, '.match',
        dataset=dataset.name, link=link.id,
        limit=10)

    # HACK: Fetch only the values on the selected page.
    value_objs = Value.id_map(dataset, map(lambda (c,v,s): v,
        pager.query[pager.offset:pager.offset+pager.limit]))
    for i, (c,v,s) in enumerate(pager.query):
        if v in value_objs:
            pager.query[i] = (c, value_objs.get(v), s)

    html = render_template('link/match.html',
            dataset=dataset, link=link, choices=pager,
            random=random)
    choice = 'INVALID' if link.is_invalid else link.entity_id
    if len(choices) and choice is None:
        c, v, s = choices[0]
        choice = 'INVALID' if s <= 50 else v.id
    return htmlfill.render(html, force_defaults=False,
            defaults={'choice': choice,
                      'name': link.name,
                      'query': request.args.get('query', ''),
                      'random': random})

@section.route('/<dataset>/links/<link>/match', methods=['POST'])
def match_save(dataset, link):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    link = Link.find(dataset, link)
    random = request.form.get('random')=='True'
    data = request_content()
    try:
        link.match(dataset, data, request.account)
        db.session.commit()
    except Invalid, inv:
        return handle_invalid(inv, match, data=data, 
                              args=[dataset.name, link.id, random])

    flash("Matched: %s" % link.name, "success")
    format = response_format()
    if format == 'json':
        return jsonify(link)
    if random:
        return match_random(dataset.name)
    else:
        return match(dataset.name, link.id)

