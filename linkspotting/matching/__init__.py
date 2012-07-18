
from linkspotting.core import db
from linkspotting.model import Value

from linkspotting.matching.normalize import normalize
from linkspotting.matching.levenshtein import levenshtein
from linkspotting.matching.fw import fw

ALGORITHMS = {
        'levenshtein': levenshtein,
        'fuzzywuzzy': fw
    }

def get_algorithms():
    algorithms = []
    for name, fn in ALGORITHMS.items():
        algorithms.append((name, fn.__doc__))
    return algorithms

def get_candidates(dataset):
    for value in Value.all(dataset):
        yield value.value, value
        if dataset.match_links:
            for link in value.links:
                yield link.key, value

def match(text, dataset, query=None):
    query = '' if query is None else query.strip().lower()
    text_normalized = normalize(text, dataset)
    matches = []
    func = ALGORITHMS.get(dataset.algorithm, levenshtein)
    for candidate, value in get_candidates(dataset):
        candidate_normalized = normalize(candidate, dataset)
        if len(query) and query not in candidate_normalized.lower():
            continue
        score = func(text_normalized, candidate_normalized)
        matches.append((candidate, value, score))
    matches = sorted(matches, key=lambda (c,v,s): s, reverse=True)
    values = []
    matches_uniq = []
    for c,v,s in matches:
        if v in values:
            continue
        values.append(v)
        matches_uniq.append((c,v,s))
    return matches_uniq


