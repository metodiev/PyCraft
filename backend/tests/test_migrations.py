"""Schema management: migrations, stamping and drift detection.

These run against real temporary databases rather than a fixture, because the
whole point is how the schema is actually built. The three cases are the ones
that occur in practice: a fresh database, one created before migrations existed,
and one already under migration control.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.db import session as dbsession
from app.db.base import Base
from app.db.migrations import prepare_schema
from sqlalchemy import create_engine, inspect, text

BACKEND = Path(__file__).resolve().parents[1]
CHALLENGES = BACKEND.parent / "challenges"


def settings_for(db_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        challenges_dir=CHALLENGES,
        execution_backend="local",
        auto_migrate=True,
    )


def table_names(db_path: Path) -> set[str]:
    connection = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()


def build_with_create_all(db_path: Path) -> None:
    """Simulate a database created by the pre-migration code path."""
    import app.models  # noqa: F401  (registers the tables)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    engine.dispose()


@pytest.mark.asyncio
async def test_a_fresh_database_is_built_by_migrations(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
    finally:
        await dbsession.dispose_engine()

    names = table_names(db_path)
    # Every model table, plus the marker that says migrations own this schema.
    assert set(Base.metadata.tables) <= names
    assert "alembic_version" in names


@pytest.mark.asyncio
async def test_a_database_with_no_models_gets_the_full_schema(tmp_path: Path) -> None:
    """The empty case must produce exactly the model's tables, no more."""
    db_path = tmp_path / "empty.db"
    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
    finally:
        await dbsession.dispose_engine()

    names = table_names(db_path) - {"alembic_version"}
    assert names == set(Base.metadata.tables)


@pytest.mark.asyncio
async def test_a_predates_migrations_database_is_stamped_not_recreated(tmp_path: Path) -> None:
    """The important upgrade path: an existing install must not break.

    Such a database already has every table but no marker, so ``upgrade`` would
    try to create tables that exist. It must be stamped instead — and stamping
    is only safe because the schema provably matches the models.
    """
    db_path = tmp_path / "legacy.db"
    build_with_create_all(db_path)
    assert "alembic_version" not in table_names(db_path)

    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)   # must not raise
    finally:
        await dbsession.dispose_engine()

    names = table_names(db_path)
    assert "alembic_version" in names
    assert set(Base.metadata.tables) <= names


@pytest.mark.asyncio
async def test_stamping_leaves_the_existing_data_alone(tmp_path: Path) -> None:
    """Stamping records a revision; it must never touch rows."""
    db_path = tmp_path / "keep.db"
    build_with_create_all(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO challenges (id, title, summary, difficulty, track, module,"
                " python_version, time_limit_ms, memory_limit_mb, points, order_index,"
                " skills, entry_file, tests_summary, kind, created_at, updated_at)"
                " VALUES ('c1', 'T', '', 'easy', 't', 'm', '3.12', 1, 1, 1, 0,"
                " '[]', 'solution.py', '', 'challenge', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()

    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
    finally:
        await dbsession.dispose_engine()

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM challenges").fetchone()[0] == 1
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_prepare_schema_is_idempotent(tmp_path: Path) -> None:
    """Startup runs every boot, so a second call must be a no-op."""
    db_path = tmp_path / "twice.db"
    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
        before = table_names(db_path)
        await prepare_schema(settings)   # must not raise
        await prepare_schema(settings)
        after = table_names(db_path)
    finally:
        await dbsession.dispose_engine()

    assert before == after


@pytest.mark.asyncio
async def test_a_partially_applied_schema_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    """A hand-altered database must not be silently stamped as correct.

    Stamping here would record a revision the database does not actually match,
    so every later migration would be applied on a false premise.
    """
    db_path = tmp_path / "odd.db"
    build_with_create_all(db_path)

    # Drop a column the models expect, by rewriting the table.
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE challenges RENAME COLUMN kind TO legacy_kind"))
    engine.dispose()

    settings = settings_for(db_path)
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
    finally:
        await dbsession.dispose_engine()

    # It refused to stamp, so no version marker was invented.
    assert "alembic_version" not in table_names(db_path)


@pytest.mark.asyncio
async def test_auto_migrate_off_reports_instead_of_changing_the_schema(tmp_path: Path) -> None:
    """With migrations owned by a release step, the app only observes."""
    db_path = tmp_path / "manual.db"
    settings = settings_for(db_path).model_copy(update={"auto_migrate": False})
    dbsession.init_engine(settings)
    try:
        await prepare_schema(settings)
    finally:
        await dbsession.dispose_engine()

    # Nothing was created and nothing was migrated.
    assert table_names(db_path) == set()


# --- the migration script itself -----------------------------------------
def migration_config(db_path: Path) -> Config:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path}")
    return config


def test_upgrade_then_downgrade_round_trips(tmp_path: Path) -> None:
    """A migration that cannot be reversed cannot be rolled back in an incident."""
    db_path = tmp_path / "round.db"
    config = migration_config(db_path)

    command.upgrade(config, "head")
    assert set(Base.metadata.tables) <= table_names(db_path)

    command.downgrade(config, "base")
    remaining = table_names(db_path) - {"alembic_version"}
    assert remaining == set(), f"downgrade left tables behind: {remaining}"


def test_the_migrated_schema_matches_the_models(tmp_path: Path) -> None:
    """Autogenerate against a migrated database must find nothing to do.

    This is the strongest statement that the baseline migration is complete: if
    it disagreed with the models in any way, autogenerate would propose a change.
    """
    db_path = tmp_path / "drift.db"
    config = migration_config(db_path)
    command.upgrade(config, "head")

    import app.models  # noqa: F401

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)

    for table in Base.metadata.sorted_tables:
        assert table.name in inspector.get_table_names(), f"{table.name} is missing"
        live = {column["name"] for column in inspector.get_columns(table.name)}
        expected = {column.name for column in table.columns}
        assert live == expected, f"{table.name}: {live ^ expected}"
    engine.dispose()


def test_the_baseline_migration_covers_every_model_table(tmp_path: Path) -> None:
    db_path = tmp_path / "cover.db"
    command.upgrade(migration_config(db_path), "head")

    migrated = table_names(db_path) - {"alembic_version"}
    assert migrated == set(Base.metadata.tables)
