"""Online-only Alembic environment for nomenklatura's own migrations.

Applications that include these revisions via `version_locations` run their
own environment instead; this one serves `nk migrate` and autogenerating new
nomenklatura revisions.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from nomenklatura import settings
from nomenklatura.db import get_engine, make_schema_metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = make_schema_metadata()


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # `nomenklatura.migrations.upgrade` passes a connection in; the alembic
    # command line goes through the configured or default database URL.
    given: Connection | None = config.attributes.get("connection")
    if given is not None:
        run_migrations(given)
        return
    url = config.get_main_option("sqlalchemy.url") or settings.DB_URL
    with get_engine(url).begin() as connection:
        run_migrations(connection)


if context.is_offline_mode():
    raise ValueError("Offline mode is not supported. Use online mode only.")

run_migrations_online()
