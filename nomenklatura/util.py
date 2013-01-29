from datetime import datetime
from collections import defaultdict
import json
import logging

from werkzeug.exceptions import NotFound
from formencode.variabledecode import NestedVariables
from flask import Response, current_app, request
from sqlalchemy.orm.query import Query
from pylibmc import Error as MCError

from nomenklatura.pager import Pager
from nomenklatura.core import memcache

KEY_RANGE = 10

MIME_TYPES = {
        'text/html': 'html',
        'application/xhtml+xml': 'html',
        'application/json': 'json',
        'text/javascript': 'json',
        }

log = logging.getLogger(__name__)

def candidate_cache_key(dataset):
    return str(dataset.name + '::c')

def candidate_hash(prefix, candidate):
    c, v = candidate
    if not len(c):
        return str(0)
    return prefix + str(ord(c[0]) % KEY_RANGE)

def cache_get(key):
    try:
        keys = [key + str(k) for k in range(KEY_RANGE)]
        values = memcache.get_multi(keys)
        if not len(values):
            return None
        vs = []
        for cands in values.values():
            vs.extend(cands)
        return vs
    except MCError, me:
        log.exception(me)


def cache_set(key, values):
    try:
        data = defaultdict(list)
        for v in values:
            data[candidate_hash(key, v)].append(v)
        memcache.set_multi(data)
    except MCError, me:
        log.exception(me)

def add_candidate_to_cache(dataset, candidate, value_id):
    try:
        prefix = candidate_cache_key(dataset)
        k = candidate_hash(prefix, (candidate, value_id))
        candidates = memcache.get(k)
        candidates.append((candidate, value_id))
        memcache.set(k, candidates)
    except MCError, me:
        log.exception(me)

def flush_cache(dataset):
    flush_candidate_cache(dataset)

def flush_candidate_cache(dataset):
    try:
        prefix = candidate_cache_key(dataset)
        keys = [prefix + str(k) for k in range(KEY_RANGE)]
        memcache.delete_multi(keys)
    except MCError, me:
        log.exception(me)

def request_format(request):
    """ 
    Determine the format of the request content. This is slightly 
    ugly as Flask has excellent request handling built in and we 
    begin to work around it.
    """
    return MIME_TYPES.get(request.content_type, 'html')

def request_content():
    """
    Handle a request and return a generator which yields all rows 
    in the incoming set.
    """
    format = request_format(request)
    if format == 'json':
        return json.loads(request.data)
    else:
        data = request.form if request.method == 'POST' \
                else request.args
        return NestedVariables().to_python(data)

class JSONEncoder(json.JSONEncoder):
    """ This encoder will serialize all entities that have a to_dict
    method by calling that method and serializing the result. """

    def encode(self, obj):
        if hasattr(obj, 'as_dict'):
            obj = obj.as_dict()
        return super(JSONEncoder, self).encode(obj)

    def default(self, obj):
        if hasattr(obj, 'as_dict'):
            return obj.as_dict()
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Query):
            return list(obj)
        if isinstance(obj, Pager):
            return list(obj)
        raise TypeError("%r is not JSON serializable" % obj)

def jsonify(obj, status=200, headers=None):
    """ Custom JSONificaton to support obj.to_dict protocol. """
    return Response(json.dumps(obj, cls=JSONEncoder), headers=headers,
                    status=status, mimetype='application/json')

# quite hackish:
def _response_format_from_path(request):
    # This means: using <format> for anything but dot-notation is really 
    # a bad idea here. 
    adapter = current_app.create_url_adapter(request)
    try:
        return adapter.match()[1].get('format')
    except NotFound:
        return None

def response_format():
    """  Use HTTP Accept headers (and suffix workarounds) to 
    determine the representation format to be sent to the client.
    """
    fmt = _response_format_from_path(request)
    if fmt in MIME_TYPES.values():
        return fmt
    neg = request.accept_mimetypes.best_match(MIME_TYPES.keys())
    return MIME_TYPES.get(neg)

