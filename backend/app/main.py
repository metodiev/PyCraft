"""FastAPI application factory and lifespan wiring.

Startup order matters: the challenge catalogue is loaded and indexed *before*
the execution backend comes up, and a failure to reach the sandbox is reported
clearly rather than surfacing as a confusing per-submission error.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ai,
    auth,
    authoring,
    challenges,
    dashboard,
    gamification,
    github,
    runtime,
    submissions,
    tutorials,
)
from app.core.config import Settings, get_settings
from app.db.migrations import prepare_schema
from app.db.session import dispose_engine, get_session_factory, init_engine
from app.execution.base import ExecutionBackend
from app.execution.docker_backend import DockerExecutionBackend
from app.execution.local_backend import LocalExecutionBackend
from app.execution.models import ExecutionError
from app.models import Challenge
from app.services.challenges import ChallengeFormatError, ChallengeRepository
from app.services.tutorials import TutorialRepository
from app.services.workers import WorkerPool

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)


def build_execution_backend(settings: Settings) -> ExecutionBackend:
    if settings.execution_backend == "docker":
        return DockerExecutionBackend(settings)
    return LocalExecutionBackend(settings)


async def _sync_challenge_index(settings: Settings, repository: ChallengeRepository) -> None:
    """Upsert the on-disk challenge catalogue into the database."""
    loaded = repository.load_all()
    for problem in repository.errors:
        logger.error("Challenge content problem: %s", problem)

    async with get_session_factory()() as session:
        for challenge in loaded:
            row = await session.get(Challenge, challenge.id)
            if row is None:
                row = Challenge(id=challenge.id)
                session.add(row)
            row.title = challenge.title
            row.summary = challenge.summary
            row.difficulty = challenge.difficulty
            row.track = challenge.track
            row.module = challenge.module
            row.python_version = challenge.python_version
            row.time_limit_ms = challenge.time_limit_ms
            row.memory_limit_mb = challenge.memory_limit_mb
            row.points = challenge.points
            row.order_index = challenge.order_index
            row.skills = challenge.skills
            row.entry_file = challenge.entry_file
            row.tests_summary = (
                f"{challenge.visible_test_count} visible, {challenge.hidden_test_count} hidden"
            )
            row.kind = challenge.kind
        await session.commit()

    logger.info("Indexed %d challenges", len(loaded))


async def _prepare_schema(settings: Settings) -> None:
    """Bring the database schema up to date, via Alembic when available.

    Migrations replace the old ``create_all`` call, which could only ever create
    tables and never evolve one — meaning any schema change required deleting a
    developer's database by hand. ``prepare_schema`` also recognises a database
    created before migrations existed and stamps it, so an existing installation
    upgrades in place instead of failing on an already-present table.
    """
    await prepare_schema(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    init_engine(settings)
    try:
        await _prepare_schema(settings)
    except Exception:
        await dispose_engine()
        raise

    repository = ChallengeRepository(settings.challenges_dir)
    try:
        await _sync_challenge_index(settings, repository)
    except (ChallengeFormatError, OSError) as exc:
        logger.error("Challenge catalogue failed to load: %s", exc)
    app.state.challenges = repository

    # Tutorials are read-only content with no database projection, so the
    # in-memory catalogue is the whole story. A failure here must not stop the
    # platform from serving challenges.
    tutorial_repository = TutorialRepository(settings.tutorials_dir)
    try:
        loaded_tutorials = tutorial_repository.load_all()
        for problem in tutorial_repository.errors:
            logger.error("Tutorial content problem: %s", problem)
        logger.info("Indexed %d tutorials", len(loaded_tutorials))
    except (OSError, ValueError) as exc:
        logger.error("Tutorial catalogue failed to load: %s", exc)
    app.state.tutorials = tutorial_repository

    # A pre-injected backend (used by tests) takes precedence over the
    # configured one, so the suite can exercise the API without a sandbox.
    backend = getattr(app.state, "execution_backend", None) or build_execution_backend(settings)
    worker_pool: WorkerPool | None = None
    try:
        await backend.start()
        app.state.execution_backend = backend
        logger.info("Execution backend: %s", backend.name)

        # Drain the submission queue in this process. Tests inject their own
        # pool (or none) so they can drive execution deterministically.
        if settings.run_workers_in_process and not getattr(app.state, "skip_workers", False):
            worker_pool = getattr(app.state, "worker_pool", None) or WorkerPool(
                settings, backend, repository
            )
            await worker_pool.start()
            app.state.worker_pool = worker_pool
    except ExecutionError as exc:
        # Keep serving the catalogue and dashboard; only Run/Submit will fail.
        logger.error("Execution backend unavailable: %s", exc)
        app.state.execution_backend = None

    try:
        yield
    finally:
        if worker_pool is not None:
            await worker_pool.stop()
        if getattr(app.state, "execution_backend", None) is not None:
            await app.state.execution_backend.stop()
        await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="PyCraft API",
        version="0.1.0",
        description=(
            "Interactive Python engineering training platform — challenges, "
            "isolated execution and progress tracking."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_routers = (
        auth.router,
        ai.router,
        github.router,
        authoring.router,
        challenges.router,
        tutorials.router,
        submissions.router,
        dashboard.router,
        gamification.router,
        runtime.router,
    )
    for router in api_routers:
        app.include_router(router, prefix=settings.api_prefix)
    # Health lives outside the versioned prefix so probes stay stable.
    app.include_router(runtime.router, include_in_schema=False)

    return app


app = create_app()
