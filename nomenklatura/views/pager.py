from urllib import urlencode

from flask import url_for, request
from flask.ext.utils.serialization import jsonify

from nomenklatura.views.common import get_limit, get_offset


SKIP_ARGS = ['limit', 'offset', '_']


def args(limit, offset):
    _args = [('limit', limit), ('offset', offset)]
    for k, v in request.args.items():
        if k not in SKIP_ARGS:
            _args.append((k, v.encode('utf-8')))
    return '?' + urlencode(_args)


def next_url(url, count, offset, limit):
    if count <= (offset + limit):
        return
    return url + args(limit, min(limit + offset, count))


def prev_url(url, count, offset, limit):
    if (offset - limit) < 0:
        return
    return url + args(limit, max(offset - limit, 0))


def query_pager(q, paginate=True, serializer=lambda x: x, **kw):
    limit = get_limit()
    offset = get_offset()
    if paginate:
        results = q.offset(offset).limit(limit)
    else:
        results = q
    url = url_for(request.endpoint, _external=True, **kw)
    count = q.count()
    data = {
        'count': count,
        'limit': limit,
        'offset': offset,
        'format': url + args('LIMIT', 'OFFSET'),
        'previous': prev_url(url, count, offset, limit),
        'next': next_url(url, count, offset, limit),
        'results': map(serializer, results)
    }
    response = jsonify(data, refs=True)
    if data['next']:
        response.headers.add_header('Link', '<%s>; rel=next' % data['next'])
    if data['previous']:
        response.headers.add_header('Link', '<%s>; rel=previous' % data['previous'])
    return response
