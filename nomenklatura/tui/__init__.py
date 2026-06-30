import logging
from typing import List, Optional, Type
from followthemoney import DS, SE, Dataset

from nomenklatura.store import Store

from nomenklatura.tui.dedupe import DedupeApp, DedupeState
from nomenklatura.tui.reconcile import ReconcileApp, ReconcileState
from nomenklatura.matching import ScoringAlgorithm
from nomenklatura.db import Session
from nomenklatura.resolver import Resolver
from nomenklatura.wikidata.client import WikidataClient
from nomenklatura.wikidata.reconcile import prepare_review
from nomenklatura.wikidata.write import QSCommand

__all__ = ["dedupe_ui", "reconcile_ui"]


def dedupe_ui(
    resolver: Resolver[SE],
    session: Session,
    store: Store[DS, SE],
    url_base: Optional[str] = None,
) -> None:
    app = DedupeApp[DS, SE]()
    app.dedupe = DedupeState(session, resolver, store, url_base=url_base)
    app.run()


def reconcile_ui(
    resolver: Resolver[SE],
    session: Session,
    store: Store[DS, SE],
    client: WikidataClient,
    dataset: Dataset,
    algorithm: Type[ScoringAlgorithm],
    aliases: bool = False,
    retrieved: Optional[str] = None,
    source_url: Optional[str] = None,
    user: Optional[str] = None,
    url_base: Optional[str] = None,
) -> List[QSCommand]:
    """Review pre-ranked Wikidata candidates and return queued commands."""
    items, commands = prepare_review(
        resolver,
        session,
        store,
        client,
        dataset,
        algorithm,
        aliases=aliases,
        retrieved=retrieved,
        source_url=source_url,
    )
    app = ReconcileApp[DS, SE]()
    app.reconcile = ReconcileState(
        session,
        resolver,
        store,
        dataset,
        items,
        commands=commands,
        retrieved=retrieved,
        source_url=source_url,
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
    return app.reconcile.commands
