from datetime import datetime
from StringIO import StringIO
import csv

from flask import Response, request
from formencode import htmlfill
from flask.ext.utils.args import arg_bool, arg_int

from nomenklatura.exc import BadRequest
from nomenklatura.util import response_format, jsonify, request_content

def handle_invalid(exc, html_func, data=None, args=()):
    format = response_format()
    if format == 'json':
        body = {'status': 400,
                'name': 'Invalid Data',
                'message': unicode(exc),
                'errors': exc.unpack_errors()}
        return jsonify(body, status=400)
    elif format == 'html':
        data = data if data is not None else request_content()
        content = htmlfill.render(html_func(*args), 
                                  defaults=data,
                                  errors=exc.unpack_errors())
        return Response(content, status=400, mimetype='text/html')
    return Response(repr(exc.unpack_errors()), status=400, 
                    mimetype='text/plain')


def get_limit(default=50):
    return max(0, min(1000, arg_int('limit', default=default)))


def get_offset(default=0):
    return max(0, arg_int('offset', default=default))


def request_data():
    data = request.json
    if data is None:
        raise BadRequest()
    return data


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


def dataset_filename(dataset, format):
    ts = datetime.utcnow().strftime('%Y%m%d')
    return '%s-%s.%s' % (dataset.name, ts, format)
