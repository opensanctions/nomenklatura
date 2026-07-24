import re
import requests
import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.util import make_session
from nomenklatura.wikidata.wikipedia import (
    fetch_summary,
    item_wikipedia_summaries,
    preferred_langs,
)

SUMMARY_URL = re.compile(r"\.wikipedia\.org/api/rest_v1/page/summary/")


def _item(*sites: str) -> Item:
    """Build an Item carrying only the named wiki sitelinks (e.g. 'enwiki')."""
    sitelinks = {
        site: {"site": site, "title": f"Title {site}", "url": f"https://{site}/x"}
        for site in sites
    }
    return Item(None, {"id": "Q1", "sitelinks": sitelinks})  # type: ignore[arg-type]


def test_preferred_langs_country_first() -> None:
    dataset = Dataset.make({"name": "wikidata"})
    person = Entity.from_data(dataset, {"schema": "Person", "id": "p"})
    person.add("nationality", "de")
    langs = preferred_langs(person)
    # The country language leads, ahead of the globally preferred set.
    assert langs[0] == "deu"
    assert "eng" in langs
    assert langs.index("deu") < langs.index("eng")
    # Deduplicated: deu appears once even though it's also in PREFERRED_LANGS.
    assert langs.count("deu") == 1


def test_preferred_langs_multilingual_country() -> None:
    dataset = Dataset.make({"name": "wikidata"})
    person = Entity.from_data(dataset, {"schema": "Person", "id": "p"})
    person.add("nationality", "ch")  # Switzerland: deu, fra, ita, roh
    langs = preferred_langs(person)
    assert langs[:4] == ["deu", "fra", "ita", "roh"]


def test_fetch_summary_negative_cache(cache_factory) -> None:
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    session = make_session()
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, status_code=404)
        assert fetch_summary(cache, session, "en", "Nobody") is None
    # A second call is served from the empty-string sentinel, no HTTP needed.
    assert fetch_summary(cache, session, "en", "Nobody") is None


def test_fetch_summary_errors_swallowed_not_cached(cache_factory) -> None:
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    session = make_session()
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, exc=requests.exceptions.ConnectionError)
        assert fetch_summary(cache, session, "en", "Flaky") is None
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, status_code=503)
        assert fetch_summary(cache, session, "en", "Flaky") is None
    # The failures left no cache entry: a working endpoint is queried again.
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, json={"extract": "A person."})
        assert fetch_summary(cache, session, "en", "Flaky") == "A person."


def test_sitelink_underscore_site_builds_hyphen_host() -> None:
    item = _item("zh_yuewiki")
    (link,) = item.wikilinks
    assert link.wiki_site == "zh-yue"
    assert link.lang == "zho"


def test_item_summaries_variant_wiki_host_and_shadowing(cache_factory) -> None:
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    session = make_session()
    # The variant wikis sort before the plain one in the API response, but the
    # plain-language wiki must win for the shared language code.
    item = _item("zh_classicalwiki", "zh_yuewiki", "zhwiki", "be_x_oldwiki")
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, json={"extract": "A person."})
        summaries = item_wikipedia_summaries(cache, session, item, ["zho", "bel"])
        assert {s.lang for s in summaries} == {"zho", "bel"}
        hosts = {r.hostname for r in m.request_history}
        # zhwiki beats the variants; be-x-old (no plain bewiki) gets a valid host.
        assert hosts == {"zh.wikipedia.org", "be-x-old.wikipedia.org"}


def test_item_summaries_preferred_only_and_capped(cache_factory) -> None:
    cache = cache_factory(Dataset.make({"name": "wikidata"}))
    session = make_session()
    # enwiki/dewiki are preferred; the made-up 'xxwiki' is not and must be skipped.
    item = _item("enwiki", "dewiki", "xxwiki")
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, json={"extract": "A person."})
        # Cap at one: only the single best-ranked language is fetched.
        summaries = item_wikipedia_summaries(
            cache, session, item, ["deu", "eng"], limit=1
        )
        assert len(summaries) == 1
        assert summaries[0].lang == "deu"
        # No fill from the non-preferred language even with budget to spare.
        many = item_wikipedia_summaries(cache, session, item, ["deu", "eng"])
        assert {s.lang for s in many} == {"deu", "eng"}
