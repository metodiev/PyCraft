"""Alembic environment.

Two things matter here beyond the stock template:

1. ``target_metadata`` is the application's ``Base.metadata``, so
   ``alembic revision --autogenerate`` sees the real models. Importing
   ``app.models`` is what registers every table; without it autogenerate would
   see an empty schema and propose dropping everything.
2. The database URL comes from the application's ``Settings``, not from
   ``alembic.ini``. A migration must run against the same database the app uses,
   and duplicating the URL in a second file is exactly how the two drift apart.

``render_as_batch`` is on because SQLite cannot drop or alter most things
in place: batch mode rewrites the table instead, so one migration works on both
SQLite and PostgreSQL.
"""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make ``app`` importable when alembic is invoked from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.models  # noqa: F401  (registers the tables on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """The database to migrate.

    The application injects the URL into the Alembic config before invoking a
    command, so the config wins when it is set. Falling back to ``Settings``
    covers a bare ``alembic upgrade head`` from the shell, where nothing has
    been injected and the environment is the only source of truth.
    """
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        # configparser escapes a literal ``%`` as ``%%``; undo that.
        return configured.replace("%%", "%")
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it against a database."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        # Detect a widened column or a changed default, rather than silently
        # treating them as unchanged.
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    # ``%`` is configparser interpolation syntax and must be escaped, or a
    # password containing one would corrupt the URL.
    configuration["sqlalchemy.url"] = _database_url().replace("%", "%%")

    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live database.

    ``asyncio.run`` cannot be called from inside a running loop, and the
    application invokes migrations during startup — which *is* a running loop.
    In that case the whole call is deferred to a worker thread, whose fresh
    thread has no loop of its own, so ``asyncio.run`` is legal there. Detecting
    and handling this is what lets the same entry point serve both a shell
    invocation and an in-process startup.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_async_migrations())
        return

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, run_async_migrations()).result()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
