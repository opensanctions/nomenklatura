from random import randint

from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect, Response
from formencode import Invalid, htmlfill, validators

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.util import jsonify, csvify, csv_filename, Pager
from nomenklatura import authz
from nomenklatura.exc import NotFound
from nomenklatura.views.common import handle_invalid
from nomenklatura.model import Dataset, Entity, Alias
from nomenklatura.matching import match as match_op

section = Blueprint('alias', __name__)


@section.route('/<dataset>/aliases.<format>', methods=['GET'])
@section.route('/<dataset>/aliases', methods=['GET'])
def index(dataset, format='json'):
    dataset = Dataset.find(dataset)
    q = Alias.all(dataset, eager=True)
    if format == 'csv':
        fn = csv_filename(dataset, 'aliases')
        headers = {
            'Content-Disposition': 'attachment; filename=' + fn
        }
        return csvify(q, headers=headers)
    return jsonify(q)


@section.route('/<dataset>/aliases/<alias>', methods=['GET'])
def view(dataset, alias):
    dataset = Dataset.find(dataset)
    alias = Alias.find(dataset, alias)
    #format = response_format()
    #if format == 'json':
    return jsonify(alias)
    #return "Not implemented!"


@section.route('/<dataset>/aliases', methods=['GET'])
def view_by_name(dataset):
    dataset = Dataset.find(dataset)
    alias = Alias.by_name(dataset, request.args.get('name'))
    if alias is None:
        raise NotFound("No such alias: %s" % request.args.get('name'))
    return view(dataset.name, alias.id)


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
        alias = Alias.lookup(dataset, data, request.account,
                             readonly=readonly)
        if alias is None:
            return jsonify({
                'is_matched': False,
                'entity': None,
                'name': data.get('name'),
                'dataset': dataset.name
                }, status=404)

        if isinstance(alias, Entity):
            return jsonify({
                'is_matched': True,
                'entity': alias,
                'name': data.get('name'),
                'dataset': dataset.name
                }, status=200)

        db.session.commit()
        status = 200 if alias.is_matched else 404
        status = 418 if alias.is_invalid else status
        return jsonify(alias, status=status)
    except Invalid, inv:
        return handle_invalid(inv, index, data=data,
                              args=[dataset.name])


@section.route('/<dataset>/match', methods=['GET'])
def match_random(dataset):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    aliases = Alias.all_unmatched(dataset)
    count = aliases.count()
    if count == 0:
        return redirect(url_for('dataset.view',
            dataset=dataset.name))
    alias = aliases.offset(randint(0, count-1)).first()
    return redirect(url_for('.match', dataset=dataset.name, alias=alias.id,
                            random=True))


@section.route('/<dataset>/aliases/<alias>/match', methods=['GET'])
def match(dataset, alias, random=False):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    alias = Alias.find(dataset, alias)
    random = random or request.args.get('random')=='True'
    choices = match_op(alias.name, dataset,
            query=request.args.get('query'))
    pager = Pager(choices, '.match',
        dataset=dataset.name, alias=alias.id,
        limit=10)

    # HACK: Fetch only the entities on the selected page.
    entities = Entity.id_map(dataset, map(lambda (c,e,s): e,
        pager.query[pager.offset:pager.offset+pager.limit]))
    for i, (c,e,s) in enumerate(pager.query):
        if e in entities:
            pager.query[i] = (c, entities.get(e), s)

    html = render_template('alias/match.html',
            dataset=dataset, alias=alias, choices=pager,
            random=random)
    choice = 'INVALID' if alias.is_invalid else alias.entity_id
    if len(choices) and choice is None:
        c, e, s = choices[0]
        choice = 'INVALID' if s <= 50 else e.id
    return htmlfill.render(html, force_defaults=False,
            defaults={'choice': choice,
                      'name': alias.name,
                      'query': request.args.get('query', ''),
                      'random': random})


@section.route('/<dataset>/aliases/<alias>/match', methods=['POST'])
def match_save(dataset, alias):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    alias = Alias.find(dataset, alias)
    random = request.form.get('random')=='True'
    data = request_content()
    try:
        alias.match(dataset, data, request.account)
        db.session.commit()
    except Invalid, inv:
        return handle_invalid(inv, match, data=data,
                              args=[dataset.name, alias.id, random])

    flash("Matched: %s" % alias.name, "success")
    format = response_format()
    if format == 'json':
        return jsonify(alias)
    if random:
        return match_random(dataset.name)
    else:
        return match(dataset.name, alias.id)
