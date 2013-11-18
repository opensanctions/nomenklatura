from datetime import datetime
from StringIO import StringIO
import csv
import logging

from werkzeug.exceptions import NotFound
from formencode.variabledecode import NestedVariables
from flask import Response, current_app, request
from flask.ext.utils.serialization import jsonify
from flask.ext.utils.args import arg_bool, arg_int


MIME_TYPES = {
        'text/html': 'html',
        'application/xhtml+xml': 'html',
        'application/json': 'json',
        'text/javascript': 'json',
        }

log = logging.getLogger(__name__)


def request_content():
    """
    Handle a request and return a generator which yields all rows 
    in the incoming set.
    """
    if request.json:
        return request.json
    else:
        data = request.form if request.method == 'POST' \
                else request.args
        return NestedVariables().to_python(data)


def csv_value(v):
    if v is None:
        return v
    if isinstance(v, datetime):
        return v.isoformat()
    return unicode(v).encode('utf-8')


def csvify(iterable, status=200, headers=None):
    rows = filter(lambda r: r is not None, [r.to_row() for r in iterable])
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

