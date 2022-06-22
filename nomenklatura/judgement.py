from enum import Enum


class Judgement(Enum):
    """A judgement of whether two entities are the same."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNSURE = "unsure"
    NO_JUDGEMENT = "no_judgement"

    def __add__(self, other: "Judgement") -> "Judgement":
        pair = {self, other}
        if pair == {Judgement.POSITIVE}:
            return Judgement.POSITIVE
        elif pair == {Judgement.POSITIVE, Judgement.NEGATIVE}:
            return Judgement.NEGATIVE
        return Judgement.UNSURE

    def to_dict(self) -> str:
        return str(self.value)
