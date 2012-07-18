from flask import Response
from formencode import htmlfill

from nomenklatura.util import response_format, jsonify

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

