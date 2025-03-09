from ast import Dict
from functools import lru_cache
from typing import Any, Optional, cast
from requests import Session
from nomenklatura.cache import Cache
from nomenklatura.wikidata.lang import LangText, pick_obj_lang
from nomenklatura.wikidata.model import Item


class WikidataClient(object):
    WD_API = "https://www.wikidata.org/w/api.php"
    LABEL_PREFIX = "wd:lb:"

    def __init__(self, cache: Cache, session: Session = None) -> None:
        self.cache = cache
        self.session = session or Session()
        self.cache.preload(f"{self.LABEL_PREFIX}%")

    def wikibase_getentities(
        self, id: str, cache_days: Optional[int] = None, **kwargs: Any
    ) -> Dict[str, Any]:
        # https://www.mediawiki.org/wiki/Wikibase/API
        # https://www.wikidata.org/w/api.php?action=help&modules=wbgetentities
        params = {**kwargs, "format": "json", "ids": id, "action": "wbgetentities"}
        data = self.http_get_json_cached(
            self.WD_API, params=params, cache_days=cache_days
        )
        return cast(Dict[str, Any], data)

    def fetch_item(self, qid: str) -> Optional[Item]:
        data = self.wikibase_getentities(qid)
        entity = data.get("entities", {}).get(qid)
        if entity is None:
            return None
        return Item(self, entity)

    @lru_cache(maxsize=100000)
    def get_label(self, qid: str) -> LangText:
        cache_key = f"{self.LABEL_PREFIX}{qid}"
        cached = self.cache.get_json(cache_key, max_age=self.label_cache_days)
        if cached is not None:
            return LangText.parse(cached)

        data = self.wikibase_getentities(
            qid,
            cache_days=0,
            props="labels",
        )
        entity = data.get("entities", {}).get(qid)
        label = pick_obj_lang(entity.get("labels", {}))
        if label.text is None:
            label.text = qid
        label.original = qid
        self.cache.set_json(cache_key, label.pack())
        return label
