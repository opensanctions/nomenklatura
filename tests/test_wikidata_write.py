from nomenklatura.wikidata.write import (
    AddStatement,
    CreateItem,
    ItemValue,
    LAST,
    MonolingualValue,
    QSValue,
    SetLabel,
    StringValue,
    TimeValue,
    serialize,
    url_reference,
)

TAB = "\t"


def test_create_block() -> None:
    """A new item with label, P31=Q5, and a sourced day-precision birth date."""
    refs = url_reference("https://example.org/source", retrieved="2026-06-14")
    birth = QSValue.date("1980-03-15")
    assert birth is not None
    commands = [
        CreateItem(),
        SetLabel(LAST, "en", "Jane Doe"),
        AddStatement(LAST, "P31", QSValue.item("Q5")),
        AddStatement(LAST, "P569", birth, references=refs),
    ]
    expected = "\n".join(
        [
            "CREATE",
            'LAST\tLen\t"Jane Doe"',
            "LAST\tP31\tQ5",
            "LAST\tP569\t+1980-03-15T00:00:00Z/11"
            "\tS854\t\"https://example.org/source\""
            "\tS813\t+2026-06-14T00:00:00Z/11",
        ]
    )
    assert serialize(commands) == expected


def test_enrich_block() -> None:
    """An existing QID gets a sourced P27 citizenship statement."""
    refs = url_reference("https://example.org/de", retrieved="2026-01-02")
    commands = [
        AddStatement("Q42", "P27", QSValue.item("Q183"), references=refs),
    ]
    expected = (
        "Q42\tP27\tQ183"
        '\tS854\t"https://example.org/de"'
        "\tS813\t+2026-01-02T00:00:00Z/11"
    )
    assert serialize(commands) == expected


def test_qualifier_and_reference_ordering() -> None:
    """Qualifiers render before references on the trailing columns."""
    cmd = AddStatement(
        "Q1",
        "P39",
        QSValue.item("Q11696"),
        qualifiers=[("P580", TimeValue("2020", 9))],
        references=[("S854", QSValue.string("https://example.org"))],
    )
    expected = (
        "Q1\tP39\tQ11696"
        "\tP580\t+2020-01-01T00:00:00Z/9"
        '\tS854\t"https://example.org"'
    )
    assert serialize([cmd]) == expected


def test_date_precision_variants() -> None:
    year = QSValue.date("1980")
    month = QSValue.date("1980-03")
    day = QSValue.date("1980-03-15")
    assert year is not None and year.render() == "+1980-01-01T00:00:00Z/9"
    assert month is not None and month.render() == "+1980-03-01T00:00:00Z/10"
    assert day is not None and day.render() == "+1980-03-15T00:00:00Z/11"


def test_date_with_time_is_day_precision() -> None:
    value = QSValue.date("1980-03-15T10:30:00")
    assert value is not None
    assert value.render() == "+1980-03-15T00:00:00Z/11"


def test_date_invalid_returns_none() -> None:
    assert QSValue.date("") is None
    assert QSValue.date("not-a-date") is None


def test_string_escaping() -> None:
    assert StringValue('He said "hi"').render() == '"He said \\"hi\\""'
    assert StringValue("a\\b").render() == '"a\\\\b"'
    assert StringValue("tab\there").render() == '"tab here"'
    assert StringValue("line\nbreak").render() == '"line break"'
    # squash_spaces collapses whitespace runs and trims leading/trailing space:
    assert StringValue("  John   Smith \n").render() == '"John Smith"'


def test_monolingual_value() -> None:
    assert MonolingualValue("en", "Hello").render() == 'en:"Hello"'
    assert MonolingualValue("de", 'a "b"').render() == 'de:"a \\"b\\""'


def test_item_value() -> None:
    assert ItemValue("Q5").render() == "Q5"


def test_label_escaping() -> None:
    cmd = SetLabel("Q1", "en", 'Quote "x"')
    assert serialize([cmd]) == 'Q1\tLen\t"Quote \\"x\\""'
