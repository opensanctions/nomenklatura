import json
from typing import Generator, Dict, Any
from followthemoney import model, EntityProxy
from followthemoney.exc import InvalidData
from followthemoney.util import PathLike

from nomenklatura.judgement import Judgement


class JudgedPair(object):
    """A pair of two entities which have been judged to be the same
    (or not) by a user."""

    __slots__ = ("left", "right", "schema", "weight", "judgement")

    def __init__(
        self, left: EntityProxy, right: EntityProxy, judgement: Judgement
    ) -> None:
        self.left = left
        self.right = right
        self.schema = model.common_schema(left.schema, right.schema)
        self.judgement = judgement
        self.weight = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "judgement": self.judgement.value,
            "weight": self.weight,
        }


def read_pairs(pairs_file: PathLike) -> Generator[JudgedPair, None, None]:
    """Read judgement pairs (training data) from a JSON file."""
    with open(pairs_file, "r") as fh:
        while line := fh.readline():
            data = json.loads(line)
            left_entity = EntityProxy.from_dict(data["left"])
            right_entity = EntityProxy.from_dict(data["right"])
            judgement = Judgement(data["judgement"])
            if judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
                continue
            try:
                yield JudgedPair(left_entity, right_entity, judgement)
            except InvalidData:
                continue
