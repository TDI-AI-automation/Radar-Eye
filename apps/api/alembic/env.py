import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from apps.api.app.config import get_settings
from apps.api.app.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False -- fileConfig()'s default (True) silently
# disables every logger that already exists in the process and isn't
# explicitly named in alembic.ini's [loggers] section. In this repository
# that includes apps/deepstream/app/stage_logging.py's radar_eye.audit
# logger (and the radar_eye.stage.* loggers) whenever Alembic runs in the
# same process as application code -- e.g. every pytest session that
# exercises both apps/api/tests/test_migrations.py and anything logging
# through those loggers afterward (apps/deepstream/tests/test_watchdog.py
# was silently broken this way from 2026-07-23 onward: the falling-edge
# audit warning became a no-op once radar_eye.audit.disabled was True).
# Alembic itself only needs its own loggers configured; disabling
# unrelated application loggers is never correct here.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# The database URL comes from application settings (env-only secrets +
# configs/settings.yaml), never from a static value in this checked-in
# alembic.ini -- see apps.api.app.config. Only resolved here if a caller
# hasn't already set one: a test (apps/api/tests/test_migrations.py)
# builds this same Config object and calls
# config.set_main_option("sqlalchemy.url", <test database url>) before
# invoking alembic.command.upgrade/downgrade, so migrations run against
# the test database with no monkeypatching of get_settings() at all.
if config.get_main_option("sqlalchemy.url") is None:
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:  # pragma: no cover
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    Unused in this repository -- migrations always run online, against a
    real engine (see run_migrations_online() below). Kept as Alembic's
    standard template scaffolding in case offline SQL-script generation is
    ever needed.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():  # pragma: no cover -- always run online, see above
    run_migrations_offline()
else:
    run_migrations_online()
