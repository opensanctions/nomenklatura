from pathlib import Path
import pickle
import logging
from itertools import combinations
from typing import Any, Dict, Generic, List, Set, Tuple
from followthemoney.types import registry

from nomenklatura.util import PathLike
from nomenklatura.resolver import Pair, Identifier
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import View
from nomenklatura.index.entry import Field
from nomenklatura.index.tokenizer import NAME_PART_FIELD, WORD_FIELD, Tokenizer


class BaseIndex(Generic[DS, CE]):
    
    def __init__(self, view: View[DS, CE]):
        self.view = view


    def build(self) -> None:
        """Index all entities in the dataset."""
        raise NotImplementedError()

    
    def match(self, entity: CE) -> List[Tuple[Identifier, float]]:
        """Match an entity against the index, returning a list of
        (entity_id, score) pairs."""
        raise NotImplementedError()
