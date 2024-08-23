import json
from typing import Generator, Dict, Any, Set, List
from followthemoney import model
from followthemoney.proxy import EntityProxy
from functools import cache

from nomenklatura.judgement import Judgement
from nomenklatura.util import PathLike


class JudgedPair(object):
    """
    A pair of two entities which have been judged to be the same
    (or not) by a user.
    """

    __slots__ = ("left", "right", "judgement", "group")

    def __init__(
        self, left: EntityProxy, right: EntityProxy, judgement: Judgement, group: int
    ) -> None:
        self.left = left
        self.right = right
        self.judgement = judgement
        self.group = group

    def to_dict(self) -> Dict[str, Any]:
        return {
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
            "judgement": self.judgement.value,
            "group": self.group,
        }


def read_pairs(pairs_file: PathLike) -> Generator[JudgedPair, None, None]:
    """Read judgement pairs (training data) from a JSON file."""
    with open(pairs_file, "r") as fh:
        while line := fh.readline():
            data = json.loads(line)
            left_entity = EntityProxy.from_dict(model, data["left"])
            right_entity = EntityProxy.from_dict(model, data["right"])
            judgement = Judgement(data["judgement"])
            if judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
                continue
            yield JudgedPair(left_entity, right_entity, judgement, data["group"])


def read_pair_sets(pairs_file: PathLike) -> List[Set[JudgedPair]]:
    sets: List[Set[JudgedPair]] = []
    with open(pairs_file, "r") as fh:
        while line := fh.readline():
            pair_array = json.loads(line)
            pair_set: Set[JudgedPair] = set()
            for pair_dict in pair_array:
                left_entity = EntityProxy.from_dict(model, pair_dict["left"])
                right_entity = EntityProxy.from_dict(model, pair_dict["right"])
                judgement = Judgement(pair_dict["judgement"])
                if judgement not in (Judgement.POSITIVE, Judgement.NEGATIVE):
                    continue
                pair_set.add(JudgedPair(left_entity, right_entity, judgement))
            sets.append(pair_set)
    return sets
    