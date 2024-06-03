import json
import requests_mock
from normality import slugify
from nomenklatura.cache import Cache
from nomenklatura.dataset import Dataset
from nomenklatura.enrich import get_enricher
from nomenklatura.enrich.common import Enricher
from nomenklatura.enrich.wikidata import clean_name
from nomenklatura.enrich.wikidata.lang import LangText
from nomenklatura.entity import CompositeEntity

from ..conftest import FIXTURES_PATH

PATH = "nomenklatura.enrich.wikidata:WikidataEnricher"
dataset = Dataset.make({"name": "wikidata", "title": "Wikidata"})


def wd_read_response(request, context):
    """Read a local file if it exists, otherwise download it. This is not
    so much a mocker as a test disk cache."""
    file_name = slugify(request.url.split("/w/")[-1], sep="_")
    path = FIXTURES_PATH / f"wikidata/{file_name}.json"
    if not path.exists():
        import urllib.request

        data = json.load(urllib.request.urlopen(request.url))
        for _, value in data["entities"].items():
            value.pop("sitelinks", None)
            for sect in ["labels", "aliases", "descriptions"]:
                # labels = value.get("labels", {})
                for lang in list(value.get(sect, {}).keys()):
                    if lang != "en":
                        del value[sect][lang]
        with open(path, "w") as fh:
            json.dump(data, fh)
    with open(path, "r") as fh:
        return json.load(fh)


def load_enricher():
    enricher_cls = get_enricher(PATH)
    assert enricher_cls is not None, PATH
    assert issubclass(enricher_cls, Enricher)
    cache = Cache.make_default(dataset)
    return enricher_cls(dataset, cache, {})


def test_wikidata_match():
    enricher = load_enricher()

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        ent = CompositeEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        assert results[0].id == "Q7747", results[0]

    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        data = {
            "schema": "Person",
            "id": "xxx",
            "properties": {"wikidataId": ["Q7747"]},
        }
        ent = CompositeEntity.from_data(dataset, data)
        results = list(enricher.match(ent))
        assert len(results) == 1, results
        assert results[0].id == "Q7747", results[0]


def test_wikidata_enrich():
    enricher = load_enricher()
    with requests_mock.Mocker(real_http=False) as m:
        m.register_uri(
            "GET",
            "https://www.wikidata.org/w/api.php",
            json=wd_read_response,
        )
        ent = CompositeEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
        adjacent = list(enricher.expand(ent, ent))
        assert len(adjacent) > 3, adjacent


def test_model_apply():
    ent = CompositeEntity.from_data(dataset, {"schema": "Person", "id": "Q7747"})
    text = LangText("test", "en")
    text.apply(ent, "name")
    assert ent.get("name") == ["test"]

    only_dirty = LangText("(placeholder)", "en")
    only_dirty.apply(ent, "alias", clean=clean_name)
    assert ent.get("alias") == []

    dirty = LangText("clean part (politician)", "en")
    dirty.apply(ent, "alias", clean=clean_name)
    assert ent.get("alias") == ["clean part"]
