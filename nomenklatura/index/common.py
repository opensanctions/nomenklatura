from pathlib import Path
from typing import Generic, Iterable, List, Tuple
from followthemoney import DS, SE
from nomenklatura.resolver import Identifier
from nomenklatura.store import View


class BaseIndex(Generic[DS, SE]):
    MAX_PAIRS = 10_000
    name: str

    def __init__(self, view: View[DS, SE], data_dir: Path) -> None:
        raise NotImplementedError

    def build(self) -> None:
        raise NotImplementedError

    def pairs(
        self, max_pairs: int = MAX_PAIRS
    ) -> Iterable[Tuple[Tuple[Identifier, Identifier], float]]:
        raise NotImplementedError

    def match(self, entity: SE) -> List[Tuple[Identifier, float]]:
        raise NotImplementedError
