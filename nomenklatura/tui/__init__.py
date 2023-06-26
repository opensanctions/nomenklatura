from typing import Optional
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import Store

from nomenklatura.tui.app import DedupeApp, DedupeState

__all__ = ["dedupe_ui"]


def dedupe_ui(store: Store[DS, CE], url_base: Optional[str] = None) -> None:
    app = DedupeApp()
    app.dedupe = DedupeState(store, url_base=url_base)
    app.run()
