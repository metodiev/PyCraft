"""Running migrations from application code.

Two situations have to work, and they are genuinely different:

* **A fresh database.** Run ``upgrade head`` and the schema appears.
* **A database created before migrations existed.** It already has every table
  but no ``alembic_version`` row, so ``upgrade head`` would try to ``CREATE
  TABLE`` an existing table and fail. Such a database must be *stamped* instead
  — recorded as already at this revision — and only if its schema genuinely
  matches, so a stamped database is never a lie.

The check in :func:`_schema_matches_models` is what keeps stamping honest: it
compares the live columns against the models and refuses when they differ.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_engine

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "alembic"


def _alembic_config(settings: Settings) -> Config:
    """An Alembic config pointed at this project's migrations.

    The URL is injected here rather than read from ``alembic.ini`` so the
    application and the migration tool can never disagree about which database
    they are talking about.
    """
    config = Config(str(_MIGRATIONS_DIR.parent / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def _migration_paths_available() -> bool:
    return (_MIGRATIONS_DIR / "versions").is_dir()


async def _has_version_table(connection: AsyncConnection) -> bool:
    names = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
    return "alembic_version" in set(names)


async def _existing_model_tables(connection: AsyncConnection) -> set[str]:
    """Which of the model's tables already exist.

    This is what distinguishes a fresh database from one built before
    migrations existed: a fresh one has **none** of them.
    """

    def _names(sync_conn) -> set[str]:
        return set(inspect(sync_conn).get_table_names())

    present = await connection.run_sync(_names)
    return present & set(Base.metadata.tables)


async def _schema_differences(connection: AsyncConnection) -> list[str]:
    """Missing tables or columns, as readable strings.

    An empty result means the live schema already matches the models, which is
    what makes stamping a pre-migration database safe rather than a guess.
    """

    def _compare(sync_conn) -> list[str]:
        inspector = inspect(sync_conn)
        existing = set(inspector.get_table_names())
        differences: list[str] = []
        for table in Base.metadata.sorted_tables:
            if table.name not in existing:
                differences.append(f"missing table {table.name}")
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in present:
                    differences.append(f"missing column {table.name}.{column.name}")
        return differences

    return await connection.run_sync(_compare)


async def prepare_schema(settings: Settings, *, auto_migrate: bool | None = None) -> None:
    """Bring the database schema up to date before the app serves traffic.

    Three cases, and they need different handling:

    * **Fresh database** — nothing of ours exists yet, so ``upgrade head``
      builds it.
    * **Predates migrations** — every table already matches the models but
      there is no ``alembic_version`` marker. Stamping it to the current
      revision lets future migrations apply cleanly; without this, ``upgrade``
      would try to create tables that already exist.
    * **Already versioned** — just upgrade.

    ``auto_migrate`` defaults to :attr:`Settings.auto_migrate`. When it is off,
    the schema is only *checked*: an operator runs ``alembic upgrade head``
    themselves, and the app reports drift rather than silently serving against
    a stale database.
    """
    if auto_migrate is None:
        auto_migrate = settings.auto_migrate

    if not _migration_paths_available():
        logger.warning("No migrations directory found; falling back to create_all()")
        engine = get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        return

    engine = get_engine()
    async with engine.connect() as connection:
        already_versioned = await _has_version_table(connection)
        existing = await _existing_model_tables(connection)
        differences = await _schema_differences(connection)

    is_fresh = not existing
    matches = not differences

    if not auto_migrate:
        if not already_versioned and not is_fresh:
            logger.error(
                "The database schema is not managed by migrations (%d difference(s) "
                "from the models). Run:  alembic upgrade head",
                len(differences),
            )
        elif differences:
            logger.error(
                "The database schema is out of date (%d difference(s)). Run:  "
                "alembic upgrade head",
                len(differences),
            )
        return

    config = _alembic_config(settings)

    if already_versioned:
        # Alembic decides what is left to do; a no-op when already at head.
        await asyncio.to_thread(command.upgrade, config, "head")
        logger.info("Database schema is up to date")
        return

    if is_fresh:
        await asyncio.to_thread(command.upgrade, config, "head")
        logger.info("Database schema created")
        return

    if matches:
        # Built by create_all before migrations existed. Every table matches, so
        # recording it at head is accurate rather than optimistic.
        await asyncio.to_thread(command.stamp, config, "head")
        logger.info(
            "Database predates migrations; stamped as the current revision "
            "(schema already matches the models)"
        )
        return

    # Partially built or altered by hand. Guessing here risks data loss, so say
    # exactly what is wrong and leave it to a human.
    preview = ", ".join(differences[:6])
    logger.error(
        "The database has tables that do not match the models, and is not under "
        "migration control: %s%s. Resolve this manually — run  alembic stamp head  "
        "if the differences are known and intentional, or migrate the data into a "
        "fresh database.",
        preview,
        " ..." if len(differences) > 6 else "",
    )
