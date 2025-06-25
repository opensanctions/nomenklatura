from typing import List
from rigour.names import Name, NamePart

from nomenklatura.matching.logic_v2.names.distance import (
    weighted_edit_similarity as wes,
)


def pt(name: str) -> List[NamePart]:
    return Name(name).parts


def test_weighted_similarity():
    assert wes(pt("Vladimir Putin"), pt("Vladimir Putin")) == 1.0
    assert wes(pt(""), pt("Putin, Vladimir")) == 0.0

    dbase = wes(pt("Putin, Vladimir"), pt("Putin, Vladimar"))
    assert dbase < 1.0
    assert dbase > 0.5

    dsimilar = wes(pt("Putin, Vladimir"), pt("Putin, Vladim1r"))
    assert dsimilar > dbase

    dspace = wes(pt("Putin, Vladimir"), pt("PutinVladimir"))
    assert dspace < 1.0
    assert dspace > dbase
