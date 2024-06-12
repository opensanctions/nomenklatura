from pathlib import Path
from typing import Generator, Generic, List, Tuple
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View


class BaseIndex(Generic[DS, CE]):
    name: str

    def __init__(self, view: View[DS, CE], data_dir: Path) -> None:
        raise NotImplementedError

    def build(self) -> None:
        raise NotImplementedError

    def pairs(self) -> List[Tuple[Tuple[Identifier, Identifier], float]]:
        raise NotImplementedError

    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        raise NotImplementedError
