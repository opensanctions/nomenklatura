import time 
import logging 

from nomenklatura.util import candidate_cache_key, cache_get, cache_set
from nomenklatura.model import Entity
from nomenklatura.matching.normalize import normalize

log = logging.getLogger(__name__)


def _get_candidates(dataset):
    for entity in Entity.all(dataset, eager_aliases=dataset.match_aliases):
        candidate = normalize(entity.name, dataset)
        yield candidate, entity.id
        if dataset.match_aliases:
            for link in entity.aliases_static:
                candidate = normalize(link.name, dataset)
                yield candidate, entity.id

def get_candidates(dataset):
    begin = time.time()
    key = candidate_cache_key(dataset)
    cand = cache_get(key)
    if cand is None:
        cand = list(set(_get_candidates(dataset)))
        cache_set(key, cand)

    duration = time.time() - begin
    log.info("Fetching %s candidates took: %sms",
            len(cand), duration*1000)
    return cand

