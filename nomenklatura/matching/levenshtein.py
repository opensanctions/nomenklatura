
def levenshtein(text, candidate):
    """ Generic Levenshtein distance """
    from Levenshtein import distance
    l = min(len(text), len(candidate))
    return l - distance(text, candidate)
