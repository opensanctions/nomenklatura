import json
from functools import lru_cache
from typing import Any, Optional, Dict
from requests import Session
from rigour.urls import build_url
from nomenklatura.cache import Cache
from nomenklatura.wikidata.lang import LangText, pick_obj_lang
from nomenklatura.wikidata.model import Item


class WikidataClient(object):
    WD_API = "https://www.wikidata.org/w/api.php"
    LABEL_PREFIX = "wd:lb:"
    LABEL_CACHE_DAYS = 100

    def __init__(
        self, cache: Cache, session: Optional[Session] = None, cache_days: int = 14
    ) -> None:
        self.cache = cache
        self.session = session or Session()
        self.cache_days = cache_days
        self.cache.preload(f"{self.LABEL_PREFIX}%")

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
        res = self.session.get(self.WD_API, params=params)
        res.raise_for_status()
        data: Dict[str, Any] = res.json()
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return LangText(None)
        label = pick_obj_lang(entity.get("labels", {}))
        if label.text is None:
            label.text = qid
        label.original = qid
        self.cache.set_json(cache_key, label.pack())
        return label
