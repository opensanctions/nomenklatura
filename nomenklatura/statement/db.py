from sqlalchemy import MetaData, Table, Column, DateTime, Unicode, Boolean

KEY_LEN = 255
VALUE_LEN = 65535


def make_statement_table(metadata: MetaData, name: str = "statement") -> Table:
    return Table(
        name,
        metadata,
        Column("id", Unicode(KEY_LEN), primary_key=True, unique=True),
        Column("entity_id", Unicode(KEY_LEN), index=True, nullable=False),
        Column("canonical_id", Unicode(KEY_LEN), index=True, nullable=True),
        Column("prop", Unicode(KEY_LEN), nullable=False),
        Column("prop_type", Unicode(KEY_LEN), nullable=False),
        Column("schema", Unicode(KEY_LEN), nullable=False),
        Column("value", Unicode(VALUE_LEN), nullable=False),
        Column("original_value", Unicode(VALUE_LEN), nullable=True),
        Column("dataset", Unicode(KEY_LEN), index=True),
        Column("lang", Unicode(KEY_LEN), nullable=True),
        Column("target", Boolean, default=False, nullable=False),
        Column("external", Boolean, default=False, nullable=False),
        Column("first_seen", DateTime, nullable=False),
        Column("last_seen", DateTime, index=True),
    )
