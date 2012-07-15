from datetime import datetime
import json

from werkzeug.exceptions import NotFound
from formencode.variabledecode import NestedVariables
from flask import Response, current_app, request
from sqlalchemy.orm.query import Query

MIME_TYPES = {
        'text/html': 'html',
        'application/xhtml+xml': 'html',
        'application/json': 'json',
        'text/javascript': 'json',
        }

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
        nv = NestedVariables()
        return nv.to_python(request.form)

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

