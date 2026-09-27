"""Runtime information — which Python versions and sandbox the platform uses."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import RepositoryDep, SettingsDep
from app.schemas import RuntimeInfo

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
