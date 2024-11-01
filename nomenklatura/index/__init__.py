import logging
from pathlib import Path
from typing import Type, Optional

from nomenklatura.index.index import Index
from nomenklatura.index.common import BaseIndex
from nomenklatura.store import View
from nomenklatura.dataset import DS
from nomenklatura.entity import CE

log = logging.getLogger(__name__)
INDEX_TYPES = ["tantivy", "duckdb", Index.name]


def get_index(
    view: View[DS, CE], path: Path, type_: Optional[str]
) -> BaseIndex[DS, CE]:
    """Get the best available index class to use."""
    clazz: Type[BaseIndex[DS, CE]] = Index[DS, CE]
    if type_ == "tantivy":
        try:
            from nomenklatura.index.tantivy_index import TantivyIndex

            clazz = TantivyIndex[DS, CE]
        except ImportError:
            log.warning("`tantivy` is not available, falling back to in-memory index.")
    if type_ == "duckdb":
        try:
            from nomenklatura.index.duckdb_index import DuckDBIndex

            clazz = DuckDBIndex[DS, CE]
        except ImportError:
            log.warning("`tantivy` is not available, falling back to in-memory index.")

    index = clazz(view, path)
    index.build()
    return index


__all__ = ["BaseIndex", "Index", "TantivyIndex", "DuckDBIndex", "get_index"]
