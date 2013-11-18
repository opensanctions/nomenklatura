import re
import json

from formencode import FancyValidator, Invalid
from sqlalchemy.types import TypeDecorator, VARCHAR

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


class JsonType(TypeDecorator):
    """Represents an immutable structure as a json-encoded string."""

    impl = VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)

        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value
