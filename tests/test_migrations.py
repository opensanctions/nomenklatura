from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from nomenklatura.db import get_engine, make_schema_metadata
from nomenklatura.migrations import upgrade


def test_migrations_match_metadata(tmp_path: Path):
    """The migrations create exactly the tables nomenklatura declares."""
    engine = get_engine(f"sqlite:///{tmp_path / 'migrated.db'}")
    upgrade(engine)
    # A second run on an up-to-date database is a no-op.
    upgrade(engine)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, make_schema_metadata()) == []
