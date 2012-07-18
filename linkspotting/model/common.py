import re
import json

from formencode import FancyValidator, Invalid
import sqlalchemy.types as types

VALID_NAME = re.compile(r"^[a-zA-Z0-9_\-]{2,1999}$")

class Name(FancyValidator):
    """ Check if a given name is valid for datasets. """

    def _to_python(self, value, state):
        if VALID_NAME.match(value):
            return value
        raise Invalid('Invalid name.', value, None)

class DataBlob(FancyValidator):
    """ Check if a given name is valid for datasets. """

    def _to_python(self, value, state):
        if isinstance(value, dict):
            return value
        raise Invalid('Invalid data.', value, None)

class JsonType(types.MutableType, types.TypeDecorator):
    impl = types.Unicode

    def process_bind_param(self, value, engine):
        return unicode(json.dumps(value))

    def process_result_value(self, value, engine):
        if value:
            return json.loads(value)
        else:
            # default can also be a list
            return {}

    def copy_value(self, value):
        return json.loads(json.dumps(value))

