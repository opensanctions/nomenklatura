import re
import requests_mock
from followthemoney import Dataset
from followthemoney import StatementEntity as Entity

from nomenklatura.cache import Cache
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


def test_fetch_summary_negative_cache() -> None:
    cache = Cache.make_default(Dataset.make({"name": "wikidata"}))
    session = make_session()
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri("GET", SUMMARY_URL, status_code=404)
        assert fetch_summary(cache, session, "en", "Nobody") is None
    # A second call is served from the empty-string sentinel, no HTTP needed.
    assert fetch_summary(cache, session, "en", "Nobody") is None
    cache.close()


def test_item_summaries_preferred_only_and_capped() -> None:
    cache = Cache.make_default(Dataset.make({"name": "wikidata"}))
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
    cache.close()
