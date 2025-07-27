import json
import logging
from functools import lru_cache
from typing import Any, List, Optional, Dict
from requests import Session
from normality import squash_spaces
from rigour.urls import build_url
from nomenklatura.cache import Cache
from nomenklatura.wikidata.lang import LangText
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.query import SparqlResponse

log = logging.getLogger(__name__)


class WikidataClient(object):
    WD_API = "https://www.wikidata.org/w/api.php"
    QUERY_API = "https://query.wikidata.org/sparql"
    QUERY_HEADERS = {
        "Accept": "application/sparql-results+json",
    }
    CACHE_SHORT = 1
    CACHE_MEDIUM = CACHE_SHORT * 7
    CACHE_LONG = CACHE_SHORT * 30

    LABEL_PREFIX = "wd:lb:"
    LABEL_CACHE_DAYS = 100

    def __init__(
        self, cache: Cache, session: Optional[Session] = None, cache_days: int = 14
    ) -> None:
        self.cache = cache
        self.session = session or Session()
        self.cache_days = cache_days
        # self.cache.preload(f"{self.LABEL_PREFIX}%")

    @lru_cache(maxsize=1000)
    def fetch_item(self, qid: str) -> Optional[Item]:
        # https://www.mediawiki.org/wiki/Wikibase/API
        # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
        params = {"format": "json", "ids": qid, "action": "wbgetentities"}
        url = build_url(self.WD_API, params=params)
        raw = self.cache.get(url, max_age=self.cache_days)
        if raw is None:
            res = self.session.get(url)
            res.raise_for_status()
            raw = res.text
            self.cache.set(url, raw)
        data = json.loads(raw)
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return None
        return Item(self, entity)

    @lru_cache(maxsize=100000)
    def get_label(self, qid: str) -> LangText:
        cache_key = f"{self.LABEL_PREFIX}{qid}"
        cached = self.cache.get_json(cache_key, max_age=self.LABEL_CACHE_DAYS)
        if cached is not None:
            return LangText.parse(cached)
        params = {
            "format": "json",
            "ids": qid,
            "action": "wbgetentities",
            "props": "labels",
        }
        url = build_url(self.WD_API, params=params)
        res = self.session.get(url)
        res.raise_for_status()
        data: Dict[str, Any] = res.json()
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return LangText(None)
        labels = LangText.from_dict(entity.get("labels", {}))
        label = LangText.pick(labels)
        if label is None:
            label = LangText(qid)
        label.original = qid
        self.cache.set_json(cache_key, label.pack())
        return label

    def query(self, query_text: str) -> SparqlResponse:
        """Query the Wikidata SPARQL endpoint."""
        clean_text = squash_spaces(query_text)
        if len(clean_text) == 0:
            raise RuntimeError("Invalid query: %r" % query_text)
        params = {"query": clean_text}
        url = build_url(self.QUERY_API, params=params)
        raw = self.cache.get(url, max_age=self.cache_days)
        if raw is None:
            res = self.session.get(url, headers=self.QUERY_HEADERS)
            res.raise_for_status()
            raw = res.text
            self.cache.set(url, raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as err:
            self.cache.delete(url)
            log.exception("Failed to parse JSON: %s", err)
            return SparqlResponse(clean_text, {})
        return SparqlResponse(clean_text, data)

    @lru_cache(maxsize=30000)
    def _type_props(self, qid: str) -> List[str]:
        item = self.fetch_item(qid)
        if item is None:
            return []
        types: List[str] = []
        for claim in item.claims:
            # historical countries are always historical:
            ended = claim.qualifiers.get("P582") is not None and claim.qid != "Q3024240"
            if ended or claim.qid is None:
                continue
            if claim.property in ("P31", "P279"):
                types.append(claim.qid)
        return types

    def __repr__(self) -> str:
        return "<WikidataClient()>"

    def __hash__(self) -> int:
        return 42
