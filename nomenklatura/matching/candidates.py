import time 
import logging 

from nomenklatura.model import Entity
from nomenklatura.matching.normalize import normalize

log = logging.getLogger(__name__)


def get_candidates(dataset):
    for entity in Entity.all(dataset, eager_aliases=dataset.match_aliases):
        candidate = normalize(entity.name, dataset)
        yield candidate, entity.id
        if dataset.match_aliases:
            for link in entity.aliases_static:
                candidate = normalize(link.name, dataset)
                yield candidate, entity.id
