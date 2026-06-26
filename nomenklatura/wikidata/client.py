import json
import logging
from functools import lru_cache
from typing import Any, List, Optional, Dict, Set
from requests import Session
from normality import squash_spaces
from rigour.urls import build_url
from rigour.util import MEMO_SMALL
from rigour.ids.wikidata import is_qid
from followthemoney import StatementEntity, registry
from followthemoney.settings import USER_AGENT
from nomenklatura.cache import Cache
from nomenklatura.wikidata.util import make_session
from nomenklatura.wikidata.lang import LangText
from nomenklatura.wikidata.model import Item
from nomenklatura.wikidata.query import SparqlResponse

log = logging.getLogger(__name__)


class WikidataClient(object):
    WD_API = "https://www.wikidata.org/w/api.php"
    QUERY_API = "https://query.wikidata.org/sparql"
    QUERY_HEADERS = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
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
        # A bare session gets 403'd (default UA) and throttled by Wikidata, so
        # default to a configured session with a descriptive UA and retries.
        self.session = session or make_session()
        self.cache_days = cache_days
        # self.cache.preload(f"{self.LABEL_PREFIX}%")

    @lru_cache(maxsize=MEMO_SMALL)
    def fetch_item(
        self,
        qid: str,
        cache_days: Optional[int] = None,
        randomize: bool = True,
    ) -> Optional[Item]:
        # https://www.mediawiki.org/wiki/Wikibase/API
        # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
        params = {
            "format": "json",
            "ids": qid,
            "action": "wbgetentities",
            # Ask for sitelink URLs for proper wikipedia links:
            "props": "info|sitelinks/urls|aliases|labels|descriptions|claims|datatype",
        }
        url = build_url(self.WD_API, params=params)
        cache_days = cache_days or self.cache_days
        raw = self.cache.get(url, max_age=cache_days, randomize=randomize)
        if raw is None:
            log.debug("Cache MISS fetching Wikidata item: %s cache_days=%s", qid, cache_days)
            res = self.session.get(url)
            res.raise_for_status()
            raw = res.text
            self.cache.set(url, raw)
        else:
            log.debug("Cache HIT fetching Wikidata item: %s cache_days=%s", qid, cache_days)
        data = json.loads(raw)
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return None
        item = Item(self, entity)
        if item.id != qid:
            # Redirected/merged item:
            return self.fetch_item(item.id, cache_days=cache_days, randomize=randomize)
        return item

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

    def query(
        self, query_text: str, cache_days: Optional[int] = None
    ) -> SparqlResponse:
        """Query the Wikidata SPARQL endpoint.

        Args:
          cache_days: overrides the client-level default for this call.
        """
        clean_text = squash_spaces(query_text)
        if len(clean_text) == 0:
            raise RuntimeError("Invalid query: %r" % query_text)
        params = {"query": clean_text}
        url = build_url(self.QUERY_API, params=params)
        effective_cache = cache_days if cache_days is not None else self.cache_days
        raw = self.cache.get(url, max_age=effective_cache)
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
            return SparqlResponse(
                clean_text, {"head": {"vars": []}, "results": {"bindings": []}}
            )
        return SparqlResponse(clean_text, data)

    def search_items(
        self, entity: StatementEntity, aliases: bool = False, limit: int = 7
    ) -> List[str]:
        """Find Wikidata QIDs that might be the same as an OpenSanctions entity.

        Reach for this when reconciling an OS entity against Wikidata: it runs the
        entity's names through the `wbsearchentities` API and returns candidate
        QIDs for a downstream matcher to rank. It returns only QIDs — the caller
        decides which items to fetch and how to project them — so the client stays
        decoupled from the matcher's needs.

        All `name` values are searched. With `aliases`, the search also covers
        aliases (every matchable name-type value), trading more API calls for
        better recall on transliterated or aliased names. `limit` is the per-name
        result cap (the `wbsearchentities` default is 7, max 50); raise it for
        better recall on common names.
        """
        if aliases:
            names = entity.get_type_values(registry.name, matchable=True)
        else:
            names = entity.get("name", quiet=True)
        qids: List[str] = []
        seen: Set[str] = set()
        for name in names:
            for qid in self._search_name(name, limit=limit):
                if qid not in seen:
                    seen.add(qid)
                    qids.append(qid)
        return qids

    def _search_name(self, name: str, limit: int = 7) -> List[str]:
        if not name.strip():
            return []
        params = {
            "format": "json",
            "action": "wbsearchentities",
            "type": "item",
            "language": "en",
            "strictlanguage": "false",
            "limit": str(limit),
            "search": name,
        }
        url = build_url(self.WD_API, params=params)
        raw = self.cache.get(url, max_age=self.cache_days)
        if raw is None:
            res = self.session.get(url)
            res.raise_for_status()
            raw = res.text
            self.cache.set(url, raw)
        data = json.loads(raw)
        results = data.get("search")
        if results is None:
            # A response without a `search` key is malformed/transient; don't
            # keep it around to be served from cache.
            self.cache.delete(url)
            log.info("Wikidata search has no results: %s", name)
            return []
        qids: List[str] = []
        for result in results:
            qid = result.get("id")
            if qid is not None and is_qid(qid):
                qids.append(qid)
        return qids

    @lru_cache(maxsize=30000)
    def _type_props(self, qid: str) -> List[str]:
        item = self.fetch_item(qid)
        if item is None:
            return []
        types: List[str] = []
        for claim in item.claims:
            # historical countries are always historical:
            ended = claim.is_ended and claim.qid != "Q3024240"
            if ended or claim.qid is None or claim.deprecated:
                continue
            if claim.property in ("P31", "P279"):
                types.append(claim.qid)
        return types

    def __repr__(self) -> str:
        return "<WikidataClient()>"

    def __hash__(self) -> int:
        return 42
