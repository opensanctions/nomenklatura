import json 

from flask import Blueprint, request, url_for
from flask.ext.utils.serialization import jsonify

from nomenklatura.exc import BadRequest
from nomenklatura.model import Dataset, Entity
from nomenklatura.views.common import get_limit, get_offset
from nomenklatura.model.matching import find_matches


section = Blueprint('reconcile', __name__)


def reconcile_index(dataset):
    domain = url_for('index', _external=True).strip('/')
    urlp = domain + '/entities/{{id}}'
    meta = {
        'name': 'nomenklatura: %s' % dataset.label,
        'identifierSpace': 'http://rdf.freebase.com/ns/type.object.id',
        'schemaSpace': 'http://rdf.freebase.com/ns/type.object.id',
        'view': {'url': urlp},
        'preview': {
            'url': urlp + '?preview=true', 
            'width': 600,
            'height': 300
        },
        'suggest': {
            'entity': {
                'service_url': domain,
                'service_path': '/api/2/datasets/' + dataset.name + '/suggest'
            }
        },
        'defaultTypes': [{'name': dataset.label, 'id': '/' + dataset.name}]
    }
    return jsonify(meta)


def reconcile_op(dataset, query):
    try:
        limit = max(1, min(100, int(query.get('limit'))))
    except:
        limit = 5

    matches = find_matches(dataset, query.get('query', ''))
    matches = matches.limit(limit)

    results = []
    for match in matches:
        results.append({
            'name': match['entity'].name,
            'score': match['score'],
            'type': [{
                'id': '/' + dataset.name,
                'name': dataset.label
                }],
            'id': match['entity'].id,
            'uri': url_for('entities.view', id=match['entity'].id, _external=True),
            'match': match['score']==100
        })
    return {
        'result': results, 
        'num': len(results)
        }


@section.route('/datasets/<dataset>/reconcile', methods=['GET', 'POST'])
def reconcile(dataset):
    """
    Reconciliation API, emulates Google Refine API. See: 
    http://code.google.com/p/google-refine/wiki/ReconciliationServiceApi
    """
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


@section.route('/datasets/<dataset>/suggest', methods=['GET', 'POST'])
def suggest(dataset):
    """ 
    Suggest API, emulates Google Refine API. See:
    http://code.google.com/p/google-refine/wiki/SuggestApi
    """
    dataset = Dataset.by_name(dataset)
    entities = Entity.all().filter(Entity.invalid!=True)
    query = request.args.get('prefix', '').strip()
    entities = entities.filter(Entity.name.ilike('%s%%' % query))
    entities = entities.offset(get_offset(field='start'))
    entities = entities.limit(get_limit(default=20))

    matches = []
    for entity in entities:
        matches.append({
            'name': entity.name,
            'n:type': {
                'id': '/' + dataset.name,
                'name': dataset.label
                },
            'id': entity.id
            })
    return jsonify({
        "code" : "/api/status/ok",
        "status" : "200 OK",
        "prefix" : query,
        "result" : matches
        })
