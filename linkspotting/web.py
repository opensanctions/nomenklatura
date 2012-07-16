from flask import render_template, Response, request
from formencode import Invalid

from linkspotting.core import app, db
from linkspotting.model import Dataset
from linkspotting.util import jsonify, response_format
from linkspotting.views.dataset import section as dataset
from linkspotting.views.value import section as value
from linkspotting.views.link import section as link

@app.context_processor
def set_template_globals():
    return {
        'datasets': Dataset.all()
        }

@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(410)
@app.errorhandler(500)
def handle_exceptions(exc):
    """ Re-format exceptions to JSON if accept requires that. """
    format = response_format()
    if format == 'json':
        body = {'status': exc.code,
                'name': exc.name,
                'message': exc.get_description(request.environ)}
        return jsonify(body, status=exc.code,
                       headers=exc.get_headers(request.environ))
    return exc

app.register_blueprint(dataset)
app.register_blueprint(value)
app.register_blueprint(link)

@app.route('/')
def index():
    return render_template('index.html')
