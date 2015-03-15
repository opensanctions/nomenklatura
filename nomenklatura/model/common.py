import re
# import json
from uuid import uuid4

from formencode import FancyValidator, Invalid
# from sqlalchemy.types import TypeDecorator, VARCHAR

VALID_NAME = re.compile(r"^[a-zA-Z0-9_\-]{2,1999}$")


def make_key():
    return unicode(uuid4())


class Name(FancyValidator):
    """ Check if a given name is valid for datasets. """

    def _to_python(self, value, state):
        if VALID_NAME.match(value):
            return value
        raise Invalid('Invalid name.', value, None)
