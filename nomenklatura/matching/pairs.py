from typing import Generic
from followthemoney.dedupe import Judgement

from nomenklatura.entity import E


class JudgedPair(Generic[E]):
    __slots__ = ("left", "right", "judgement")

    def __init__(self, left: E, right: E, judgement: Judgement):
        self.left = left
        self.right = right
        self.judgement = judgement
