import re
import pytest
import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.cache import Cache
from nomenklatura.resolver import Resolver
from nomenklatura.store import load_entity_file_store
from nomenklatura.matching import EntityResolveRegression
from nomenklatura.wikidata import Claim, LangText, WikidataClient
from nomenklatura.wikidata.reconcile import candidate_proxy, reconcile
from nomenklatura.enrich.wikidata import clean_wikidata_name

from .conftest import wd_read_response


def _wd_dispatch(search_results):
    """Mock callback: serve search results for wbsearchentities, fixtures else."""

    def handler(request, context):
        if "wbsearchentities" in request.qs.get("action", []):
            return {"search": search_results}
        return wd_read_response(request, context)

    return handler


def test_lang_text():
    text1 = LangText("John Smith", "eng")
    text2 = LangText("John Smith", "ara")
    assert text1 != text2

    text2 = LangText("John Smith", "eng")
    assert text1 == text2


def test_model_apply():
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    ent = Entity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
    text = LangText("test", "en")
    text.apply(ent, "name")
    assert ent.get("name") == ["test"]

    only_dirty = LangText("(placeholder)", "en")
    only_dirty.apply(ent, "alias", clean=clean_wikidata_name)
    assert ent.get("alias") == ["(placeholder)"]
    ent.pop("alias")

    dirty = LangText("clean part (politician)", "en")
    dirty.apply(ent, "alias", clean=clean_wikidata_name)
    assert ent.get("alias") == ["clean part"]
    ent.pop("alias")


def test_client_query(test_cache: Cache):
    data = {
        "head": {"vars": ["person"]},
        "results": {
            "bindings": [
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q23",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q42",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q76",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q80",
                    }
                },
                {
                    "person": {
                        "type": "uri",
                        "value": "http://www.wikidata.org/entity/Q91",
                    }
                },
            ]
        },
    }
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            WikidataClient.QUERY_API,
            json=data,
        )
        client = WikidataClient(test_cache)
        with pytest.raises(RuntimeError):
            client.query("  ")

        query = "SELECT ?person WHERE { ?person wdt:P31 wd:Q5 . } LIMIT 5"
        response = client.query(query)
        assert len(response) == 5
        assert "person" in repr(response)
        for result in response.results:
            assert "Q" in repr(result)
            assert len(result.values) == 1
            assert result.plain("person") is not None


def test_search_items(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    entity = Entity.from_data(
        dataset,
        {"schema": "Person", "id": "p1", "properties": {"name": ["Vladimir Putin"]}},
    )
    search = {
        "search": [
            {"id": "Q7747", "label": "Vladimir Putin"},
            {"id": "Q1058", "label": "someone else"},
            # Non-QID ids (e.g. property/lexeme hits) are filtered out:
            {"id": "P31", "label": "instance of"},
            {"label": "no id at all"},
        ]
    }
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=search)
        client = WikidataClient(test_cache)
        qids = client.search_items(entity)
        assert qids == ["Q7747", "Q1058"]

    # Empty result set: no `search` key returns no candidates and isn't cached.
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json={})
        client = WikidataClient(test_cache)
        empty = Entity.from_data(
            dataset,
            {"schema": "Person", "id": "p2", "properties": {"name": ["Nobody Here"]}},
        )
        assert client.search_items(empty) == []


def test_search_items_limit(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    entity = Entity.from_data(
        dataset,
        {"schema": "Person", "id": "p1", "properties": {"name": ["Someone"]}},
    )
    seen = {}

    def handler(request, context):
        seen["limit"] = request.qs.get("limit", [None])[0]
        return {"search": [{"id": "Q1"}]}

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=handler)
        client = WikidataClient(test_cache)
        client.search_items(entity, limit=3)
    assert seen["limit"] == "3"


def test_search_items_aliases(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    entity = Entity.from_data(
        dataset,
        {
            "schema": "Person",
            "id": "p3",
            "properties": {"name": ["Joe Biden"], "alias": ["Joseph Biden"]},
        },
    )

    def by_name(request, context):
        name = request.qs.get("search", [""])[0]
        if "joseph" in name:
            return {"search": [{"id": "Q6279"}, {"id": "Q12345"}]}
        return {"search": [{"id": "Q6279"}]}

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=by_name)
        client = WikidataClient(test_cache)
        # Default: only the name is searched, not the alias.
        assert client.search_items(entity) == ["Q6279"]
        # aliases=True also searches the alias; hits unioned, de-duplicated:
        assert client.search_items(entity, aliases=True) == ["Q6279", "Q12345"]


def test_make_session():
    from followthemoney.settings import USER_AGENT
    from nomenklatura.wikidata.util import make_session

    session = make_session()
    # Wikimedia 403s the default requests UA; ours must be descriptive.
    assert session.headers["User-Agent"] == USER_AGENT
    retries = session.get_adapter("https://www.wikidata.org/").max_retries
    assert retries.total == 3
    # Back off on rate-limit / Retry-After statuses:
    assert 429 in retries.status_forcelist
    assert 503 in retries.status_forcelist


def test_client_user_agent(test_cache: Cache):
    from followthemoney.settings import USER_AGENT

    # The client's default session carries our UA (set via make_session).
    client = WikidataClient(test_cache)
    assert client.session.headers["User-Agent"] == USER_AGENT


def test_candidate_proxy(test_cache: Cache):
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=wd_read_response)
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q7747")
        assert item is not None
        proxy = candidate_proxy(dataset, item)
        assert proxy is not None
        assert proxy.schema.name == "Person"
        assert proxy.id == "Q7747"
        assert "Vladimir Putin" in proxy.get("name")
        assert proxy.get("birthDate") == ["1952-10-07"]
        assert proxy.get("gender") == ["male"]
        # P27 maps to citizenship; Putin holds Soviet (historical) + Russian:
        assert "ru" in proxy.get("citizenship")


def test_reconcile_auto(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-putin", "schema": "Person", '
        '"properties": {"name": ["Vladimir Putin"], "birthDate": ["1952-10-07"]}}\n'
        '{"id": "os-nobody", "schema": "Person", '
        '"properties": {"name": ["Jane Q Nobody"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})

    cache = cache_factory(dataset)
    with requests_mock.Mocker(real_http=False) as m:
        # Both persons' searches return Putin's QID; only the real Putin scores.
        m.register_uri(
            "GET",
            WikidataClient.WD_API,
            json=_wd_dispatch([{"id": "Q7747"}]),
        )
        client = WikidataClient(cache)
        commands = reconcile(
            resolver, db_session, store, client, dataset, EntityResolveRegression,
            threshold=0.5, create=True,
        )
        # Without create=True the unmatched person yields no create commands.
        no_create = reconcile(
            resolver, db_session, store, client, dataset, EntityResolveRegression,
            threshold=0.5, create=False,
        )

    # The matching person is linked to the QID; the non-matching one is not.
    assert resolver.get_canonical("os-putin") == "Q7747"
    assert resolver.get_canonical("os-nobody") == "os-nobody"

    # create=True yields a CREATE for the miss; create=False yields none.
    from nomenklatura.wikidata.write import CreateItem

    assert any(isinstance(c, CreateItem) for c in commands)
    assert not any(isinstance(c, CreateItem) for c in no_create)

def test_entity_qid():
    from nomenklatura.wikidata.util import entity_qid

    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    # A Wikidata-sourced entity carries the QID as its own id:
    by_id = Entity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
    assert entity_qid(by_id) == "Q7747"

    # A cross-referenced entity carries it in the wikidataId property:
    by_prop = Entity.from_data(
        dataset,
        {"schema": "Person", "id": "os-1", "properties": {"wikidataId": ["Q42"]}},
    )
    assert entity_qid(by_prop) == "Q42"

    # The id wins over the property when both are present:
    both = Entity.from_data(
        dataset,
        {"schema": "Person", "id": "Q7747", "properties": {"wikidataId": ["Q42"]}},
    )
    assert entity_qid(both) == "Q7747"

    # An unlinked reconciliation candidate has neither:
    none = Entity.from_data(dataset, {"schema": "Person", "id": "os-2"})
    assert entity_qid(none) is None


def test_reconcile_wikidata_id(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    # A person already linked via the wikidataId property is enriched, not
    # re-searched or proposed for creation.
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-putin", "schema": "Person", "properties": '
        '{"name": ["Vladimir Putin"], "wikidataId": ["Q7747"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    cache = cache_factory(dataset)
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=wd_read_response)
        client = WikidataClient(cache)
        commands = reconcile(
            resolver, db_session, store, client, dataset, EntityResolveRegression, threshold=0.5
        )
    # No CREATE for a linked entity; enrichment was attempted against Q7747.
    from nomenklatura.wikidata.write import CreateItem

    assert not any(isinstance(c, CreateItem) for c in commands)

def _reconcile_state(resolver, session, store, cache):
    from nomenklatura.tui.reconcile import ReconcileState
    from nomenklatura.wikidata.reconcile import prepare_review

    dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})
    client = WikidataClient(cache)
    items, commands = prepare_review(
        resolver, session, store, client, dataset, EntityResolveRegression
    )
    return ReconcileState(session, resolver, store, dataset, items, commands=commands)


def test_create_preview():
    from nomenklatura.wikidata.reconcile import create_preview

    dataset = Dataset.make({"name": "wikidata"})
    person = Entity.from_data(dataset, {"schema": "Person", "id": "os-x"})
    person.add("name", "Jane Doe")
    person.add("birthDate", "1970-01-01")
    # A placeholder stub, not a projection of the person's values.
    preview = create_preview(dataset, person)
    assert preview.get("name") == ["[NEW ITEM]"]
    assert preview.get("birthDate") == []


def test_reconcile_state_confirm(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-putin", "schema": "Person", "properties": '
        '{"name": ["Vladimir Putin"], "birthDate": ["1952-10-07"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=_wd_dispatch([{"id": "Q7747"}]))
        m.register_uri(
            "GET",
            re.compile(r"\.wikipedia\.org/api/rest_v1/page/summary/"),
            json={"extract": "Vladimir Putin is a politician."},
        )
        state = _reconcile_state(resolver, db_session, store, cache)
        assert state.start() is True
        assert state.person is not None
        assert state.candidates[0][0].id == "Q7747"
        # Highlight the top candidate and confirm the match.
        state.highlight = 0
        state.confirm()
    assert resolver.get_canonical("os-putin") == "Q7747"

def test_reconcile_state_create(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-nobody", "schema": "Person", '
        '"properties": {"name": ["Jane Q Nobody"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    with requests_mock.Mocker(real_http=False) as m:
        # No search hits: the only row is "None of the above".
        m.register_uri("GET", WikidataClient.WD_API, json=_wd_dispatch([]))
        state = _reconcile_state(resolver, db_session, store, cache)
        assert state.start() is True
        assert state.candidates == []
        assert state.at_create is True
        state.confirm()
    from nomenklatura.wikidata.write import CreateItem

    assert any(isinstance(c, CreateItem) for c in state.commands)
    assert resolver.get_canonical("os-nobody") == "os-nobody"

def test_reconcile_state_skip(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-nobody", "schema": "Person", '
        '"properties": {"name": ["Jane Q Nobody"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=_wd_dispatch([]))
        state = _reconcile_state(resolver, db_session, store, cache)
        assert state.start() is True
        state.skip()
    assert state.commands == []
    assert resolver.get_canonical("os-nobody") == "os-nobody"

def test_reconcile_state_linked_skipped(tmp_path, resolver: Resolver[Entity], cache_factory, db_session):
    # A person already linked via wikidataId is enriched silently, gets no screen.
    path = tmp_path / "entities.ijson"
    path.write_text(
        '{"id": "os-putin", "schema": "Person", "properties": '
        '{"name": ["Vladimir Putin"], "wikidataId": ["Q7747"]}}\n'
    )
    store = load_entity_file_store(path, resolver=resolver)
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=wd_read_response)
        state = _reconcile_state(resolver, db_session, store, cache)
        # No reviewable person; the linked one was enriched during load.
        assert state.start() is False
        assert state.person is None

def test_fetch_item_no_such_entity(test_cache: Cache):
    # A deleted/never-created QID is a permanent miss: None, and the error
    # response stays cached so later runs don't refetch it.
    error = {"error": {"code": "no-such-entity", "id": "Q404"}}
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=error)
        client = WikidataClient(test_cache)
        assert client.fetch_item("Q404") is None
        assert m.call_count == 1
        # A fresh client (empty lru) is served from the SQL cache:
        client2 = WikidataClient(test_cache)
        assert client2.fetch_item("Q404") is None
        assert m.call_count == 1


def test_fetch_item_transient_error(test_cache: Cache):
    # A persistent in-band API error is retried, then skipped (None) and never
    # cached, so a transient failure can't masquerade as a missing item for
    # cache_days: a later run refetches it.
    error = {"error": {"code": "maxlag", "info": "database is lagged"}}
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=error)
        client = WikidataClient(test_cache)
        client.API_RETRY_BACKOFF = 0  # don't sleep between retries in tests
        assert client.fetch_item("Q7747") is None
        assert m.call_count == WikidataClient.API_MAX_ATTEMPTS
    # A fresh client (empty lru) refetches from source and succeeds, proving the
    # transient failure was not written to the SQL cache:
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=wd_read_response)
        client2 = WikidataClient(test_cache)
        item = client2.fetch_item("Q7747")
        assert m.call_count == 1
        assert item is not None
        assert item.id == "Q7747"


def test_fetch_item_transient_recovers(test_cache: Cache):
    # A transient error that clears within the retry budget resolves to the
    # item in a single fetch_item call, without surfacing an exception.
    error = {"error": {"code": "maxlag", "info": "database is lagged"}}
    calls = {"n": 0}

    def handler(request, context):
        calls["n"] += 1
        if calls["n"] < 2:
            return error
        return wd_read_response(request, context)

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=handler)
        client = WikidataClient(test_cache)
        client.API_RETRY_BACKOFF = 0  # don't sleep between retries in tests
        item = client.fetch_item("Q7747")
        assert item is not None
        assert item.id == "Q7747"
        assert m.call_count > 1


def test_types_missing_ancestor(test_cache: Cache):
    # A deleted P31/P279 ancestor is skipped, not an AssertionError.
    def handler(request, context):
        # requests_mock lower-cases query string values:
        qid = request.qs["ids"][0].upper()
        if qid == "Q1000":
            claim = {
                "id": "Q1000$1",
                "rank": "normal",
                "mainsnak": {
                    "snaktype": "value",
                    "property": "P31",
                    "datatype": "wikibase-item",
                    "datavalue": {
                        "type": "wikibase-entityid",
                        "value": {"id": "Q2000"},
                    },
                },
            }
            return {"entities": {"Q1000": {"id": "Q1000", "claims": {"P31": [claim]}}}}
        return {"error": {"code": "no-such-entity", "id": qid}}

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=handler)
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q1000")
        assert item is not None
        assert item.types == {"Q1000", "Q2000"}


def _time_snak(prop: str, time: str, precision: int = 11):
    return {
        "snaktype": "value",
        "property": prop,
        "datatype": "time",
        "datavalue": {"type": "time", "value": {"time": time, "precision": precision}},
    }


def test_item_deprecated_claims(test_cache: Cache):
    # Deprecated rank marks known-wrong values; they parse into `deprecated`,
    # not `claims`, so no consumer reads them as facts.
    claims = {
        "P569": [
            {
                "id": "Q3000$1",
                "rank": "normal",
                "mainsnak": _time_snak("P569", "+1952-10-07T00:00:00Z"),
            },
            {
                "id": "Q3000$2",
                "rank": "deprecated",
                "mainsnak": _time_snak("P569", "+1852-10-07T00:00:00Z"),
            },
        ]
    }
    entity = {"entities": {"Q3000": {"id": "Q3000", "claims": claims}}}
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", WikidataClient.WD_API, json=entity)
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q3000")
        assert item is not None
        assert [c.text.text for c in item.claims] == ["1952-10-07"]
        assert len(item.deprecated) == 1
        assert item.deprecated[0].text.text == "1852-10-07"


def test_claim_is_ended(test_cache: Cache):
    from datetime import datetime, timezone

    reference = datetime(2026, 7, 1, tzinfo=timezone.utc)
    client = WikidataClient(test_cache, reference_time=reference)
    assert client.reference_time == reference

    def claim_with_end(qualifier) -> Claim:
        data = {
            "id": "Q1$1",
            "rank": "normal",
            "mainsnak": {
                "snaktype": "value",
                "property": "P39",
                "datatype": "wikibase-item",
                "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q2"}},
            },
            "qualifiers": {"P582": [qualifier]} if qualifier else {},
        }
        return Claim(client, data, "P39")

    # No end qualifier at all:
    assert claim_with_end(None).is_ended() is False
    # An elapsed end date:
    assert claim_with_end(_time_snak("P582", "+2015-06-01T00:00:00Z")).is_ended() is True
    # "No value" asserts the claim is current:
    novalue = {"snaktype": "novalue", "property": "P582", "datatype": "time"}
    assert claim_with_end(novalue).is_ended() is False
    # "Unknown value" means ended at an unknown date:
    somevalue = {"snaktype": "somevalue", "property": "P582", "datatype": "time"}
    assert claim_with_end(somevalue).is_ended() is True
    # A scheduled future end is not yet ended:
    assert claim_with_end(_time_snak("P582", "+2030-01-01T00:00:00Z")).is_ended() is False
    # A year-precision end only counts once the year has elapsed:
    current_year = _time_snak("P582", "+2026-00-00T00:00:00Z", precision=9)
    assert claim_with_end(current_year).is_ended() is False
    # An explicit reference overrides the client's:
    later = datetime(2031, 1, 1, tzinfo=timezone.utc)
    future = claim_with_end(_time_snak("P582", "+2030-01-01T00:00:00Z"))
    assert future.is_ended(reference_time=later) is True


def test_qualify_value(test_cache: Cache):
    from nomenklatura.wikidata.qualified import qualify_value

    client = WikidataClient(test_cache)
    data = {
        "id": "Q1$1",
        "rank": "normal",
        "mainsnak": {
            "snaktype": "value",
            "property": "P39",
            "datatype": "wikibase-item",
            "datavalue": {"type": "wikibase-entityid", "value": {"id": "Q30185"}},
        },
        "qualifiers": {
            "P580": [_time_snak("P580", "+2010-01-01T00:00:00Z", precision=9)],
            "P582": [_time_snak("P582", "+2015-06-01T00:00:00Z")],
        },
    }
    claim = Claim(client, data, "P39")
    value = LangText("Mayor", "eng", original="Q30185")
    qualified = qualify_value(value, claim)
    # Tenure dates are baked into the label; the QID stays as provenance:
    assert qualified.text == "Mayor (2010-2015)"
    assert qualified.original == "Q30185"
    assert qualified.lang == "eng"


def test_model(test_cache: Cache):
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            WikidataClient.WD_API,
            json=wd_read_response,
        )
        client = WikidataClient(test_cache)
        item = client.fetch_item("Q7747")
        assert item is not None
        assert item.id == "Q7747"
        assert item.label is not None
        assert item.label.text == "Vladimir Putin"
        assert len(item.sitelinks) > 2
        enwiki = [s for s in item.sitelinks if s.site == "enwiki"]
        assert len(enwiki) == 1
        assert enwiki[0].title == "Vladimir Putin"
        assert "Q5" in item.types
        birth_dates = [c for c in item.claims if c.property == "P569"]
        assert len(birth_dates) == 1
        assert birth_dates[0].text.text == "1952-10-07"
