from nomenklatura.matching.name_based.names import soundex_name_parts
from nomenklatura.matching.types import ScoringConfig

from ..factory import e

config = ScoringConfig.defaults()


def test_soundex_name_comparison():
    query = e("Person", name="Michelle Michaela")
    result = e("Person", name="Michaela Michelle Micheli")
    assert soundex_name_parts(query, result, config).score == 1.0

    result = e("Person", name="Michelle Michi")
    assert soundex_name_parts(query, result, config).score == 1.0

    result = e("Person", name="Donald Duck")
    assert soundex_name_parts(query, result, config).score == 0.0


def test_single_name():
    name = e("Person", name="Hannibal")
    other = e("Person", name="Hannibal")
    assert soundex_name_parts(name, other, config).score == 1.0

    other = e("Person", name="Hanniball")
    assert soundex_name_parts(name, other, config).score == 1.0

    other = e("Person", name="Hannibol")
    assert soundex_name_parts(name, other, config).score == 1.0
