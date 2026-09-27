"""Runtime information — which Python versions and sandbox the platform uses."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import RepositoryDep, SessionDep, SettingsDep
from app.models.submission import SubmissionStatus
from app.schemas import RuntimeInfo
from app.services import queue

router = APIRouter(tags=["runtime"])

# Versions the platform can execute. Kept explicit so the UI can show the
# runtime badge, and so adding 3.13 later is a one-line change.
SUPPORTED_PYTHON_VERSIONS = ["3.12"]
DEFAULT_PYTHON_VERSION = "3.12"


@router.get("/runtime", response_model=RuntimeInfo, summary="Execution runtime details")
async def get_runtime(
    request: Request, repository: RepositoryDep, settings: SettingsDep
) -> RuntimeInfo:
    backend = getattr(request.app.state, "execution_backend", None)
    return RuntimeInfo(
        execution_backend=backend.name if backend is not None else "unavailable",
        python_versions=SUPPORTED_PYTHON_VERSIONS,
        default_python_version=DEFAULT_PYTHON_VERSION,
        environment=settings.environment,
        challenge_count=len(repository.all()),
    )


@router.get("/health", tags=["runtime"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/queue", tags=["runtime"], summary="Submission queue depth")
async def queue_status(request: Request, session: SessionDep) -> dict[str, int | str]:
    """How much work is waiting.

    Exposed so an operator can see backpressure before learners complain, and so
    a smoke test can prove the workers are draining rather than merely running.
    """
    depth = await queue.queue_depth(session)
    pool = getattr(request.app.state, "worker_pool", None)
    backend = getattr(request.app.state, "execution_backend", None)

    waiting = int(depth.get(str(SubmissionStatus.QUEUED), 0))
    running = int(depth.get(str(SubmissionStatus.RUNNING), 0))
    return {
        "backend": backend.name if backend is not None else "unavailable",
        "workers": 0 if pool is None else pool.worker_count,
        "processed": 0 if pool is None else pool.processed,
        **depth,
        "waiting": waiting,
        "in_flight": running,
        "depth": waiting + running,
    }
