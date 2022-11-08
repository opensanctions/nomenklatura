from typing import Optional
from nomenklatura.dataset import DS
from nomenklatura.entity import CE
from nomenklatura.loader import Loader
from nomenklatura.resolver import Resolver

from nomenklatura.tui.app import DedupeApp, DedupeState

__all__ = ["dedupe_ui"]


def dedupe_ui(
    resolver: Resolver[CE], loader: Loader[DS, CE], url_base: Optional[str] = None
) -> None:
    app = DedupeApp()
    app.dedupe = DedupeState(resolver, loader, url_base=url_base)
    app.run()
