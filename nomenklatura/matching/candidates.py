import time 
import logging 

from nomenklatura.util import candidate_cache_key, cache_get, cache_set
from nomenklatura.model import Value
from nomenklatura.matching.normalize import normalize

log = logging.getLogger(__name__)


def _get_candidates(dataset):
    for value in Value.all(dataset, eager_links=dataset.match_links):
        candidate = normalize(value.name, dataset)
        yield candidate, value.id
        if dataset.match_links:
            for link in value.links_static:
                candidate = normalize(link.name, dataset)
                yield candidate, value.id

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

