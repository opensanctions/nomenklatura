import json
from typing import Generator
from followthemoney import model

from nomenklatura.entity import CompositeEntity
from nomenklatura.judgement import Judgement
from nomenklatura.util import PathLike


class JudgedPair(object):
    """A pair of two entities which have been judged to be the same
    (or not) by a user."""

    __slots__ = ("left", "right", "judgement")

    def __init__(
        self, left: CompositeEntity, right: CompositeEntity, judgement: Judgement
    ) -> None:
        self.left = left
        self.right = right
        self.judgement = judgement


def read_pairs(pairs_file: PathLike) -> Generator[JudgedPair, None, None]:
    """Read judgement pairs (training data) from a JSON file."""
    with open(pairs_file, "r") as fh:
        while line := fh.readline():
            data = json.loads(line)
            left_entity = CompositeEntity.from_dict(model, data["left"])
            right_entity = CompositeEntity.from_dict(model, data["right"])
            judgement = Judgement(data["judgement"])
            if judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
                continue
            yield JudgedPair(left_entity, right_entity, judgement)
