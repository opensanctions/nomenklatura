from flask import request

from nomenklatura.exc import Forbidden

def logged_in():
    return request.account is not None

def dataset_create():
    return logged_in()

def dataset_edit(dataset):
    if not logged_in():
        return False
    if dataset.public_edit:
        return True
    if dataset.owner_id == request.account.id:
        return True
    return False

def dataset_manage(dataset):
    if not logged_in():
        return False
    if dataset.owner_id == request.account.id:
        return True
    return False

def require(pred):
    if not pred:
        raise Forbidden("Sorry, you're not permitted to do this!")

