import logging
import time

from nomenklatura.matching.normalize import normalize
from nomenklatura.matching.levenshtein import levenshtein
from nomenklatura.matching.candidates import get_candidates

log = logging.getLogger(__name__)


def match(text, dataset, query=None):
    query = '' if query is None else query.strip()
    text_normalized = normalize(text, dataset)
    candidates = get_candidates(dataset)
    matches = []
    begin = time.time()
    for candidate, entity_id in candidates:
        if len(query) and query not in candidate.lower():
            continue
        score = levenshtein(text_normalized, candidate)
        matches.append((candidate, entity_id, score))
    matches = sorted(matches, key=lambda (c,e,s): s, reverse=True)
    entities = set()
    matches_uniq = []
    for c,e,s in matches:
        if e in entities:
            continue
        entities.add(e)
        matches_uniq.append((c,e,s))
    duration = time.time() - begin
    log.info("Matching %s candidates took: %sms",
            len(matches_uniq), duration*1000)
    return matches_uniq

def prefix_search(prefix, dataset):
    prefix_normalized = normalize(prefix, dataset)
    candidates = get_candidates(dataset)
    matches = []
    entities = set()
    for candidate, entity_id in candidates:
        if candidate.startswith(prefix_normalized):
            if entity_id not in entities:
                entities.add(entity_id)
                matches.append((candidate, entity_id))
    return matches

