import re
import pytest
import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.cache import Cache
from nomenklatura.resolver import Resolver
from nomenklatura.store import load_entity_file_store
from nomenklatura.matching import EntityResolveRegression
from nomenklatura.wikidata import WikidataClient
from nomenklatura.tui.reconcile import (
    CandidateTable,
    ReconcileApp,
    ReconcileState,
)
from nomenklatura.wikidata.reconcile import prepare_review

from .conftest import wd_read_response


def _dispatch(results):
    def handler(request, context):
        if "wbsearchentities" in request.qs.get("action", []):
            return {"search": results}
        return wd_read_response(request, context)

    return handler


# Reviewing a candidate now fetches Wikipedia summaries from the CDN REST
# endpoint; stub it so the offline tests don't hit the network.
SUMMARY_URL = re.compile(r"\.wikipedia\.org/api/rest_v1/page/summary/")


def _mock_summary(m):
    m.register_uri(
        "GET", SUMMARY_URL, json={"extract": "Vladimir Putin is a politician."}
    )


@pytest.mark.asyncio
async def test_reconcile_app_navigation(tmp_path, resolver: Resolver[Entity]):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-x", "schema": "Person", '
        '"properties": {"name": ["Vladimir Putin"]}}\n'
    )
    resolver.begin()
    store = load_entity_file_store(path, resolver=resolver)
    dataset = Dataset.make({"name": "wikidata"})
    cache = Cache.make_default(dataset)
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET", WikidataClient.WD_API, json=_dispatch([{"id": "Q7747"}])
        )
        _mock_summary(m)
        client = WikidataClient(cache)
        items, enrich = prepare_review(
            resolver, store, client, dataset, EntityResolveRegression
        )
        app = ReconcileApp[Dataset, Entity]()
        app.reconcile = ReconcileState(
            resolver, store, dataset, items, commands=enrich
        )
        async with app.run_test() as pilot:
            state = app.reconcile
            assert state.person is not None
            assert len(state.candidates) == 1
            assert state.highlight == 0
            # The candidate table, not the compare panel, holds keyboard focus.
            assert app.focused is app.query_one(CandidateTable)
            await pilot.press("down")
            assert state.highlight == 1, "down should move to 'none of the above'"
            await pilot.press("up")
            assert state.highlight == 0, "up should move back to the candidate"
    cache.close()


@pytest.mark.asyncio
async def test_reconcile_app_negative(tmp_path, resolver: Resolver[Entity]):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-x", "schema": "Person", '
        '"properties": {"name": ["Vladimir Putin"]}}\n'
    )
    resolver.begin()
    store = load_entity_file_store(path, resolver=resolver)
    dataset = Dataset.make({"name": "wikidata"})
    cache = Cache.make_default(dataset)
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET", WikidataClient.WD_API, json=_dispatch([{"id": "Q7747"}])
        )
        _mock_summary(m)
        client = WikidataClient(cache)
        items, enrich = prepare_review(
            resolver, store, client, dataset, EntityResolveRegression
        )
        app = ReconcileApp[Dataset, Entity]()
        app.reconcile = ReconcileState(
            resolver, store, dataset, items, commands=enrich
        )
        async with app.run_test() as pilot:
            state = app.reconcile
            assert len(state.candidates) == 1
            # Reject the only candidate: it's recorded NEGATIVE and removed.
            await pilot.press("n")
            assert state.candidates == []
    # The negative judgement persists so the pair won't be suggested again.
    assert resolver.get_judgement("os-x", "Q7747").value == "negative"
    cache.close()


@pytest.mark.asyncio
async def test_reconcile_app_no_candidates(tmp_path, resolver: Resolver[Entity]):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-x", "schema": "Person", '
        '"properties": {"name": ["Nobody At All"]}}\n'
    )
    resolver.begin()
    store = load_entity_file_store(path, resolver=resolver)
    dataset = Dataset.make({"name": "wikidata"})
    cache = Cache.make_default(dataset)
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=_dispatch([]))
        client = WikidataClient(cache)
        items, enrich = prepare_review(
            resolver, store, client, dataset, EntityResolveRegression
        )
        app = ReconcileApp[Dataset, Entity]()
        app.reconcile = ReconcileState(
            resolver, store, dataset, items, commands=enrich
        )
        async with app.run_test() as pilot:
            state = app.reconcile
            assert state.candidates == []
            # Cursor sits on the create row (not the "(No candidates)" note);
            # the create state is active.
            assert state.at_create is True
            # Arrowing up must not strand the cursor on the non-selectable row.
            await pilot.press("up")
            assert state.at_create is True
            # Confirming creates a new item.
            await pilot.press("x")
        from nomenklatura.wikidata.write import CreateItem

        assert any(isinstance(c, CreateItem) for c in state.commands)
    cache.close()
