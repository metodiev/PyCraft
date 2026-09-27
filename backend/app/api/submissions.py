"""Run and Submit endpoints — the core of PyCraft.

Both endpoints **queue** work and return ``202 Accepted`` immediately, so an
HTTP request is never held open for the duration of a sandbox run. Results are
collected by polling ``GET /submissions/{id}``.

That is a deliberate change from the synchronous contract this API used to have.
Previously a submission occupied a request for the whole container run, which
meant a handful of slow learners could exhaust the connection pool and hit a
proxy timeout with no way to tell the caller whether their code had run.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import BackendDep, CurrentUser, RepositoryDep, SessionDep, SettingsDep
from app.execution.models import ExecutionMode
from app.models.submission import Submission, SubmissionKind, SubmissionStatus
from app.schemas import (
    ProgressSummary,
    QueuedResponse,
    SubmissionRequest,
    SubmissionStatusResponse,
    TestResultSchema,
    reject_nested_paths,
)
from app.services import queue
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
    response_model=QueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue an experimental run",
)
async def run_challenge(
    challenge_id: str,
    payload: SubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
    backend: BackendDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> QueuedResponse:
    """Queue code for execution against the visible tests.

    Returns as soon as the work is accepted rather than holding the request open
    for the whole sandbox run. Poll ``GET /submissions/{id}`` for the output.
    """
    _reject_nested_if_single_file(repository, challenge_id, payload.files)

    service = SubmissionService(session, backend, repository, settings)
    try:
        submission = await service.enqueue(user.id, challenge_id, payload.files, ExecutionMode.RUN)
    except ChallengeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc

    depth = await queue.queue_depth(session)
    return QueuedResponse(
        submission_id=submission.id,
        status=str(submission.status),
        submission_url=f"{settings.api_prefix}/submissions/{submission.id}",
        queue_depth=sum(depth.values()),
    )


@router.post(
    "/challenges/{challenge_id}/submit",
    response_model=QueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a graded submission",
)
async def submit_challenge(
    challenge_id: str,
    payload: SubmissionRequest,
    session: SessionDep,
    user: CurrentUser,
    backend: BackendDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> QueuedResponse:
    """Queue a submission for grading, including the hidden tests.

    Progress is only updated once the queued work actually runs, so a submission
    that never executes cannot advance anyone's XP.
    """
    _reject_nested_if_single_file(repository, challenge_id, payload.files)

    service = SubmissionService(session, backend, repository, settings)
    try:
        submission = await service.enqueue(user.id, challenge_id, payload.files, ExecutionMode.SUBMIT)
    except ChallengeNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc

    depth = await queue.queue_depth(session)
    return QueuedResponse(
        submission_id=submission.id,
        status=str(submission.status),
        submission_url=f"{settings.api_prefix}/submissions/{submission.id}",
        queue_depth=sum(depth.values()),
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionStatusResponse,
    summary="Poll a submission's status and result",
)
async def get_submission(
    submission_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
    backend: BackendDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> SubmissionStatusResponse:
    """Return a submission's current state, and its result once finished.

    Scoped to the caller: another learner's submission is a 404, not a 403, so
    this endpoint cannot be used to probe which ids exist.
    """
    submission = await session.get(Submission, submission_id)
    if submission is None or submission.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown submission")

    status_value = SubmissionStatus(submission.status)
    base = SubmissionStatusResponse(
        submission_id=submission.id,
        kind=str(submission.kind),
        status=str(status_value),
        done=status_value.is_terminal,
        challenge_id=submission.challenge_id,
        created_at=submission.created_at,
        finished_at=submission.finished_at,
        error_message=submission.error_message,
        stdout=submission.stdout,
        stderr=submission.stderr,
        exit_code=submission.exit_code,
        execution_time_ms=submission.execution_time_ms,
        memory_used_mb=submission.memory_used_mb,
    )

    if not status_value.is_terminal:
        return base

    service = SubmissionService(session, backend, repository, settings)

    if submission.kind is SubmissionKind.RUN:
        return base

    outcome = await service.outcome(submission)
    scoring = outcome["scoring"]
    report = outcome["report"]

    base.score = scoring.score
    base.passed = report.passed
    base.failed = report.failed
    base.total_tests = report.total
    base.summary = scoring.summary
    base.dimensions = [d.to_dict() for d in scoring.dimensions]
    base.newly_unlocked = list(submission.unlocked or [])
    base.progress = ProgressSummary(**await service.progress_snapshot(user.id))
    base.results = [
        TestResultSchema(
            name=test.name,
            status=str(test.status),
            duration_ms=test.duration_ms,
            # Failure detail for hidden tests stays generic so the graded suite
            # cannot be reverse-engineered from the messages.
            message="" if test.hidden else test.message,
            hidden=test.hidden,
        )
        for test in report.tests
    ]
    return base
