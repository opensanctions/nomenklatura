import json 

from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect

from nomenklatura.util import jsonify
from nomenklatura.exc import BadRequest
from nomenklatura.model import Dataset, Link, Value
from nomenklatura.matching import prefix_search, match

section = Blueprint('reconcile', __name__)


def type_to_dataset(type_name):
    dataset_name = type_name.strip().strip('/')
    dataset = Dataset.by_name(dataset_name)
    if dataset is None:
        raise BadRequest('No type (or invalid type) specified!')
    return dataset

def reconcile_index(dataset):
    domain = url_for('index', _external=True).strip('/')
    urlp = domain + '{{id}}'
    meta = {
        'name': 'nomenklatura',
        'identifierSpace': 'http://rdf.freebase.com/ns/type.object.id',
        'schemaSpace': 'http://rdf.freebase.com/ns/type.object.id',
        'view': {'url': urlp},
        'preview': {
            'url': urlp + '?preview=true', 
            'width': 600,
            'height': 300
            }
        }
    if dataset is not None:
        meta['name'] = dataset.label
        meta['suggest'] = {
            'entity': {
                'service_url': domain,
                'service_path': '/' + dataset.name + '/suggest',
                'flyout_service_path': '/flyout'
                }
            }
        meta['defaultTypes'] = [{'name': dataset.label, 'id': '/' + dataset.name}]
    else:
        meta['defaultTypes'] = [{'name': d.label, 'id': '/' + d.name} for d in Dataset.all()]
    return jsonify(meta)

def reconcile_op(dataset, query):
    try:
        limit = max(1, min(100, int(query.get('limit'))))
    except ValueError: limit = 5
    except TypeError: limit = 5

    filters = [(p.get('p'), p.get('v')) for p in query.get('properties', [])]

    if dataset is None:
        dataset = type_to_dataset(query.get('type', ''))

    results = match(query.get('query', ''), dataset)[:limit]
    value_objs = Value.id_map(dataset, map(lambda (c,v,s): v, results))
    matches = []
    skip = False
    for (candidate, value_id, score) in results:
        value = value_objs[value_id]

        for key, fv in filters:
            if value.data.get(key) != fv:
                skip = True
        if skip:
            continue

        id = url_for('value.view', dataset=dataset.name, value=value.id)
        uri = url_for('value.view', dataset=dataset.name, value=value.id, _external=True)
        matches.append({
            'name': value.value,
            'score': score,
            'type': [{
                'id': '/' + dataset.name,
                'name': dataset.label
                }],
            'id': id,
            'uri': uri,
            'match': score==100
            })
    return {
        'result': matches, 
        'num': len(results)
        }

@section.route('/reconcile', methods=['GET', 'POST'])
@section.route('/<dataset>/reconcile', methods=['GET', 'POST'])
def reconcile(dataset=None):
    """
    Reconciliation API, emulates Google Refine API. See: 
    http://code.google.com/p/google-refine/wiki/ReconciliationServiceApi
    """
    if dataset is not None:
        dataset = Dataset.by_name(dataset)

    # TODO: Add proper support for types and namespacing.
    data = request.args.copy()
    data.update(request.form.copy())
    if 'query' in data:
        # single 
        q = data.get('query')
        if q.startswith('{'):
            try:
                q = json.loads(q)
            except ValueError:
                raise BadRequest()
        else:
            q = data
        return jsonify(reconcile_op(dataset, q))
    elif 'queries' in data:
        # multiple requests in one query
        qs = data.get('queries')
        try:
            qs = json.loads(qs)
        except ValueError:
            raise BadRequest()
        queries = {}
        for k, q in qs.items():
            queries[k] = reconcile_op(dataset, q)
        return jsonify(queries)
    else:
        return reconcile_index(dataset)

@section.route('/<dataset>/suggest', methods=['GET', 'POST'])
def suggest(dataset):
    """ 
    Suggest API, emulates Google Refine API. See:
    http://code.google.com/p/google-refine/wiki/SuggestApi
    """
    try:
        start = int(request.args.get('start', 0))
        limit = int(request.args.get('limit', 20))
    except:
        raise BadRequest('Invalid result range!')

    dataset = type_to_dataset(dataset)
    query = request.args.get('prefix', '').strip()
    results = prefix_search(query, dataset)[start:start+limit]
    value_objs = Value.id_map(dataset, map(lambda (c,v): v, results))
    matches = []
    for match in results:
        candidate, value_id = match
        value = value_objs[value_id]
        matches.append({
            'name': value.value,
            'n:type': {
                'id': '/' + dataset.name,
                'name': dataset.label
                },
            'id': url_for('value.view', dataset=dataset.name, value=value_id)
            })
    return jsonify({
        "code" : "/api/status/ok",
        "status" : "200 OK",
        "prefix" : query,
        "result" : matches
        })

@section.route('/flyout', methods=['GET', 'POST'])
@section.route('/private/flyout', methods=['GET', 'POST'])
def flyout():
    return jsonify({'html': '<h3>%s</h3>' % request.args.get('id')})



