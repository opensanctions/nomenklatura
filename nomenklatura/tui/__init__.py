import logging
from typing import List, Optional, Tuple, Type
from followthemoney import DS, SE, Dataset

from nomenklatura.store import Store

from nomenklatura.tui.dedupe import DedupeApp, DedupeState
from nomenklatura.tui.reconcile import ReconcileApp, ReconcileState
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.resolver import Resolver
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.write import QSCommand

__all__ = ["dedupe_ui", "reconcile_ui"]


def dedupe_ui(
    resolver: Resolver[SE], store: Store[DS, SE], url_base: Optional[str] = None
) -> None:
    app = DedupeApp[DS, SE]()
    app.dedupe = DedupeState(resolver, store, url_base=url_base)
    app.run()


def reconcile_ui(
    resolver: Resolver[SE],
    store: Store[DS, SE],
    client: WikidataClient,
    dataset: Dataset,
    algorithm: Type[ScoringAlgorithm],
    aliases: bool = False,
    retrieved: Optional[str] = None,
    user: Optional[str] = None,
    url_base: Optional[str] = None,
) -> Tuple[List[QSCommand], List[QSCommand]]:
    """Run the interactive Wikidata reconciliation UI; return the queued QS commands.

    Presents each unlinked person against its ranked Wikidata candidates for a
    human decision (confirm / create / skip) and returns the accumulated
    `(enrich_commands, create_commands)` for the caller to serialize.
    """
    app = ReconcileApp[DS, SE]()
    app.reconcile = ReconcileState(
        resolver,
        store,
        client,
        dataset,
        algorithm,
        aliases=aliases,
        retrieved=retrieved,
        user=user,
        url_base=url_base,
    )
    # Console log handlers write to the terminal Textual owns and corrupt the
    # screen; silence logging for the lifetime of the app, then restore.
    logging.disable(logging.CRITICAL)
    try:
        app.run()
    finally:
        logging.disable(logging.NOTSET)
    return app.reconcile.enrich_commands, app.reconcile.create_commands
