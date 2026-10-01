"""Alembic migrations for nomenklatura's tables.

The revisions carry the `nomenklatura` branch label. An application whose
database also hosts its own tables adds `nomenklatura:migrations/versions` to
its `version_locations`, and upgrades `heads`. A database used only by
nomenklatura is upgraded with `nk migrate`.
"""

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from nomenklatura.db import get_engine

BRANCH = "nomenklatura"


def make_config() -> Config:
    """Build an Alembic configuration for the packaged migrations."""
    config = Config()
    config.set_main_option("script_location", "nomenklatura:migrations")
    config.set_main_option("path_separator", "os")
    return config


def upgrade(engine: Engine | None = None, revision: str = f"{BRANCH}@head") -> None:
    """Apply nomenklatura's migrations to the given (or the default) database."""
    engine = engine or get_engine()
    config = make_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
