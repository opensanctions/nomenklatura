from fuzzywuzzy import fuzz

def fw(text, candidate):
    """ seatgeek's FuzzyWuzzy """
    return fuzz.ratio(text, candidate)
