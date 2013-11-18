from datetime import datetime
from collections import defaultdict
from StringIO import StringIO
import csv
import json
import logging

from werkzeug.exceptions import NotFound
from formencode.variabledecode import NestedVariables
from flask import Response, current_app, request
from sqlalchemy.orm.query import Query

from nomenklatura.pager import Pager


MIME_TYPES = {
        'text/html': 'html',
        'application/xhtml+xml': 'html',
        'application/json': 'json',
        'text/javascript': 'json',
        }

log = logging.getLogger(__name__)


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


def jsonify(obj, status=200, headers=None, shallow=False):
    """ Custom JSONificaton to support obj.to_dict protocol. """
    jsondata = JSONEncoder().encode(obj)
    if 'callback' in request.args:
        jsondata = '%s && %s(%s)' % (request.args.get('callback'),
                request.args.get('callback'), jsondata)
    return Response(jsondata, headers=headers,
                    status=status, mimetype='application/json')


def csv_value(v):
    if v is None:
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    return unicode(v).encode('utf-8')


def csvify(iterable, status=200, headers=None):
    rows = filter(lambda r: r is not None, [r.as_row() for r in iterable])
    keys = set()
    for row in rows:
        keys = keys.union(row.keys())
    buf = StringIO()
    writer = csv.writer(buf)
    writer.writerow([k.encode('utf-8') for k in keys])
    for row in rows:
        writer.writerow([csv_value(row.get(k, '')) for k in keys])
    return Response(buf.getvalue(), headers=headers,
                    status=status, mimetype='text/csv')


def csv_filename(dataset, section):
    ts = datetime.utcnow().strftime('%Y%m%d')
    return '%s_%s-%s.csv' % (dataset.name, section, ts)


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

