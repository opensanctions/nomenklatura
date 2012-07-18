
def levenshtein(text, candidate):
    """ Generic Levenshtein distance """
    from Levenshtein import distance
    l = max(len(text), len(candidate))
    return l - distance(text, candidate)
