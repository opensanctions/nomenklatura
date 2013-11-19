from flask import Blueprint, request, url_for, flash
from flask import render_template, redirect
from formencode import Invalid

from nomenklatura.core import db
from nomenklatura.util import request_content, response_format
from nomenklatura.util import jsonify, csvify, csv_filename
from nomenklatura import authz
from nomenklatura.pager import Pager
from nomenklatura.views.dataset import view as view_dataset
from nomenklatura.views.common import handle_invalid
from nomenklatura.matching import match as match_op
from nomenklatura.model import Dataset, Entity

section = Blueprint('entity', __name__)


@section.route('/<dataset>/entities/<entity>/merge', methods=['POST'])
def merge(dataset, entity):
    dataset = Dataset.find(dataset)
    authz.require(authz.dataset_edit(dataset))
    entity = Entity.find(dataset, entity)
    data = request_content()
    try:
        target = entity.merge_into(data, request.account)
        db.session.commit()
        flash("Merged %s" % entity.display_name, 'success')
        return redirect(url_for('.view', dataset=dataset.name,
                        entity=target.id))
    except Invalid, inv:
        return handle_invalid(inv, view, data=data,
                              args=[dataset.name, entity.id])

