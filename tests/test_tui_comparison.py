from followthemoney import Dataset, StatementEntity

from nomenklatura.tui.comparison import render_column


def test_render_column_marks_external_entities() -> None:
    """A candidate that is only an unverified suggestion must be visibly
    distinct from published data in the comparison header."""
    dataset = Dataset.make({"name": "comparison"})
    internal = StatementEntity(dataset, {"id": "int-1", "schema": "Person"})
    internal.add("name", "Vladimir Vladimirovich Putin")
    external = StatementEntity(dataset, {"id": "ext-1", "schema": "Person"})
    external.add("name", "Vladimir Vladimirovich Putin", external=True)

    internal_column = render_column(internal)
    assert internal_column.plain == "Person [int-1]"
    assert [s.style for s in internal_column.spans] == ["blue"]

    external_column = render_column(external)
    assert external_column.plain == "Person [ext-1] *"
    assert [s.style for s in external_column.spans] == ["yellow", "yellow bold"]
