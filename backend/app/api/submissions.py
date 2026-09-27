"""Run and Submit endpoints — the core of PyCraft."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BackendDep, CurrentUser, RepositoryDep, SessionDep, SettingsDep
from app.execution.models import ExecutionError
from app.schemas import RunResponse, SubmissionRequest, SubmitResponse, TestResultSchema
from app.services.challenges import ChallengeNotFoundError
from app.services.submissions import SubmissionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])


@router.post(
    "/challenges/{challenge_id}/run",
    response_model=RunResponse,
    summary="Execute code against the visible tests",
)
async def run_challenge(
    challenge_id: str,
    payload: SubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
    backend: BackendDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> RunResponse:
    """Run for experimentation: raw output and quick feedback, no grading."""
    service = SubmissionService(session, backend, repository, settings)
    try:
        submission, report = await service.run(user.id, challenge_id, payload.files)
    except ChallengeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc
    except ExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The execution sandbox is unavailable. Is Docker running?",
        ) from exc

    return RunResponse(
        submission_id=submission.id,
        status=str(report.status),
        stdout=report.stdout,
        stderr=report.stderr,
        exit_code=report.exit_code,
        execution_time_ms=report.execution_time_ms,
        memory_used_mb=report.memory_used_mb,
    )


@router.post(
    "/challenges/{challenge_id}/submit",
    response_model=SubmitResponse,
    summary="Grade code against the full test suite",
)
async def submit_challenge(
    challenge_id: str,
    payload: SubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
    backend: BackendDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> SubmitResponse:
    """Submit for grading, including hidden tests, and update progress."""
    service = SubmissionService(session, backend, repository, settings)
    try:
        submission, report, outcome = await service.submit(user.id, challenge_id, payload.files)
    except ChallengeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc
    except ExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The execution sandbox is unavailable. Is Docker running?",
        ) from exc

    scoring = outcome["scoring"]
    return SubmitResponse(
        submission_id=submission.id,
        status=str(report.status),
        score=scoring.score,
        passed=report.passed,
        failed=report.failed,
        total_tests=report.total,
        execution_time_ms=report.execution_time_ms,
        memory_used_mb=report.memory_used_mb,
        results=[
            TestResultSchema(
                name=test.name,
                status=str(test.status),
                duration_ms=test.duration_ms,
                # Failure detail for hidden tests stays generic so the graded
                # suite cannot be reverse-engineered from messages.
                message="" if test.hidden else test.message,
                hidden=test.hidden,
            )
            for test in report.tests
        ],
        dimensions=[d.to_dict() for d in scoring.dimensions],
        summary=scoring.summary,
        progress=outcome["progress"],
    )
