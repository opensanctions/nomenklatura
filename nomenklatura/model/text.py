import re
from unidecode import unidecode
from unicodedata import normalize as ucnorm, category
from Levenshtein import distance


REMOVE_SPACES = re.compile(r' +')


def normalize_text(text):
    if not isinstance(text, unicode):
        text = unicode(text)
    chars = []
    # http://www.fileformat.info/info/unicode/category/index.htm
    for char in ucnorm('NFKD', text):
        cat = category(char)[0]
        if cat in ['C', 'Z']:
            chars.append(u' ')
        elif cat in ['P']:
            chars.append(u'.')
        elif cat in ['M']:
            continue
        else:
            chars.append(char)
    text = u''.join(chars)
    text = REMOVE_SPACES.sub(' ', text)
    return unidecode(text).strip()


def normalize(text, dataset):
    if dataset.ignore_case:
        text = text.lower()
    if dataset.normalize_text:
        text = normalize_text(text)
    return text


def similarity(text, txet):
    l = float(max(1, min(len(text), len(txet))))
    s = (l - distance(text, txet)) / l
    return int(max(0, s*100))

