from nomenklatura.wikidata import LangText


def test_lang_text():
    text1 = LangText("John Smith", "en")
    text2 = LangText("John Smith", "ar")
    assert text1 != text2
    assert text1 > text2

    text3 = LangText("Abigail Smith", "en")
    assert text1 != text3
    assert text1 > text3

    text2 = LangText("John Smith")
    assert text1 != text2
    assert text1 > text2
