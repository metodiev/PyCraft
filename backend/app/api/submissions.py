"""Run and Submit endpoints — the core of PyCraft."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BackendDep, CurrentUser, RepositoryDep, SessionDep, SettingsDep
from app.execution.models import ExecutionError
from app.schemas import (
    RunResponse,
    SubmissionRequest,
    SubmitResponse,
    TestResultSchema,
    reject_nested_paths,
)
from app.services.achievements import unlocked_out
from app.services.challenges import ChallengeNotFoundError
from app.services.submissions import SubmissionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])


def _reject_nested_if_single_file(repository, challenge_id: str, files: dict[str, str]) -> None:
    """Nested filenames are only meaningful for project challenges."""
    try:
        challenge = repository.get(challenge_id)
    except ChallengeNotFoundError:
        # The endpoint's own 404 handling produces a better message.
        return
    if challenge.is_project:
        return
    try:
        reject_nested_paths(files)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


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
    _reject_nested_if_single_file(repository, challenge_id, payload.files)

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
    _reject_nested_if_single_file(repository, challenge_id, payload.files)

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
    unlocked = outcome.get("achievements") or []

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
        newly_unlocked=[unlocked_out(achievement) for achievement in unlocked],
    )
