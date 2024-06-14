from pathlib import Path
from typing import Generic, List, Tuple
from nomenklatura.resolver import Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View


class BaseIndex(Generic[DS, CE]):
    MAX_PAIRS = 10_000
    name: str

    def __init__(self, view: View[DS, CE], data_dir: Path) -> None:
        raise NotImplementedError

    def build(self) -> None:
        raise NotImplementedError

    def pairs(
        self, max_pairs: int = MAX_PAIRS
    ) -> List[Tuple[Tuple[Identifier, Identifier], float]]:
        raise NotImplementedError

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        raise NotImplementedError
