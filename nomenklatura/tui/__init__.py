from typing import Optional
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.store import Store

from nomenklatura.tui.app import DedupeApp, DedupeState
from nomenklatura.resolver import Resolver

__all__ = ["dedupe_ui"]


def dedupe_ui(
    resolver: Resolver[CE], store: Store[DS, CE], url_base: Optional[str] = None
) -> None:
    app = DedupeApp()
    app.dedupe = DedupeState(resolver, store, url_base=url_base)
    app.run()
