import logging
import time

from nomenklatura.core import db
from nomenklatura.matching.normalize import normalize
from nomenklatura.matching.levenshtein import levenshtein
from nomenklatura.matching.fw import fw
from nomenklatura.matching.candidates import get_candidates

log = logging.getLogger(__name__)

ALGORITHMS = {
        'levenshtein': levenshtein,
        'fuzzywuzzy': fw
    }

def get_algorithms():
    algorithms = []
    for name, fn in ALGORITHMS.items():
        algorithms.append((name, fn.__doc__))
    return algorithms

def match(text, dataset, query=None):
    query = '' if query is None else query.strip()
    text_normalized = normalize(text, dataset)
    candidates = get_candidates(dataset)
    matches = []
    begin = time.time()
    func = ALGORITHMS.get(dataset.algorithm, levenshtein)
    for candidate, value in candidates:
        if len(query) and query not in candidate.lower():
            continue
        score = func(text_normalized, candidate)
        matches.append((candidate, value, score))
    matches = sorted(matches, key=lambda (c,v,s): s, reverse=True)
    values = set()
    matches_uniq = []
    for c,v,s in matches:
        if v in values:
            continue
        values.add(v)
        matches_uniq.append((c,v,s))
    duration = time.time() - begin
    log.info("Matching %s candidates took: %sms",
            len(matches_uniq), duration*1000)
    return matches_uniq

def prefix_search(prefix, dataset):
    prefix_normalized = normalize(prefix, dataset)
    candidates = get_candidates(dataset)
    matches = []
    values = set()
    for candidate, value in candidates:
        if candidate.startswith(prefix_normalized):
            if value not in values:
                values.add(value)
                matches.append((candidate, value))
    return matches

