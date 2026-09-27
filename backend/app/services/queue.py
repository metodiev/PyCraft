"""Durable submission queue.

Submissions are rows, not messages: a learner's work must survive a restart, a
crash or a deploy. That rules out an in-memory queue and makes the database the
source of truth, with Redis (if it is ever added) serving only as a wake-up
signal.

The contract is deliberately small:

* :func:`enqueue` writes a ``queued`` row and returns immediately.
* :func:`claim` atomically takes the oldest runnable row and returns it, or
  ``None``. Two workers must never claim the same row, which is why the claim is
  a single conditional ``UPDATE`` rather than a read followed by a write.
* :func:`reclaim_expired` recovers work whose worker died mid-run.

Nothing here executes user code; that is the worker's job.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission, SubmissionStatus

logger = logging.getLogger(__name__)

#: How long a claim is valid before another worker may take the row over.
#: Must exceed the longest sandbox run, or a slow submission would be run twice.
DEFAULT_LEASE_SECONDS = 120

#: How many times a single submission may be attempted. A payload that crashes
#: its worker every time is abandoned rather than occupying the queue forever.
DEFAULT_MAX_ATTEMPTS = 3


def _now() -> datetime:
    return datetime.now(UTC)


async def enqueue(session: AsyncSession, submission: Submission) -> Submission:
    """Persist a submission as runnable work.

    The caller sets ``user_id``, ``challenge_id``, ``kind`` and ``files``; this
    fills in the queue bookkeeping and flushes so the row has an id.
    """
    submission.status = SubmissionStatus.QUEUED
    submission.attempts = 0
    submission.claimed_at = None
    submission.lease_expires_at = None
    submission.finished_at = None
    session.add(submission)
    await session.flush()
    return submission


def _claimable() -> tuple:
    """Rows a worker may take: queued, or running with an expired lease."""
    now = _now()
    return (
        or_(
            Submission.status == SubmissionStatus.QUEUED,
            (
                (Submission.status == SubmissionStatus.RUNNING)
                & (Submission.lease_expires_at.is_not(None))
                & (Submission.lease_expires_at < now)
            ),
        ),
        Submission.attempts < DEFAULT_MAX_ATTEMPTS,
    )


async def claim(
    session: AsyncSession,
    *,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Submission | None:
    """Atomically claim the oldest runnable submission, or return ``None``.

    Implemented as a conditional ``UPDATE ... WHERE id = (SELECT ...)`` so the
    check and the take are one statement. A read-then-write would let two
    workers claim the same row, which would run the learner's code twice and
    double-count their attempt.
    """
    now = _now()
    lease_until = now + timedelta(seconds=lease_seconds)

    stale_running = (
        (Submission.status == SubmissionStatus.RUNNING)
        & (Submission.lease_expires_at.is_not(None))
        & (Submission.lease_expires_at < now)
    )

    # Pick one candidate first, oldest first so the queue is fair.
    candidate = (
        select(Submission.id)
        .where(
            or_(Submission.status == SubmissionStatus.QUEUED, stale_running),
            Submission.attempts < max_attempts,
        )
        .order_by(Submission.created_at, Submission.id)
        .limit(1)
        .scalar_subquery()
    )

    statement = (
        update(Submission)
        .where(
            Submission.id == candidate,
            # Re-check the state inside the UPDATE: if another worker claimed it
            # between the subquery and this statement, this matches nothing.
            or_(Submission.status == SubmissionStatus.QUEUED, stale_running),
        )
        .values(
            status=SubmissionStatus.RUNNING,
            attempts=Submission.attempts + 1,
            claimed_at=now,
            lease_expires_at=lease_until,
        )
        .returning(Submission.id)
    )

    result = await session.execute(statement)
    claimed_id = result.scalar_one_or_none()
    if claimed_id is None:
        await session.commit()
        return None

    await session.commit()
    return await session.get(Submission, claimed_id)


async def renew(
    session: AsyncSession, submission_id, *, lease_seconds: int = DEFAULT_LEASE_SECONDS
) -> None:
    """Extend the lease on a running submission.

    A long sandbox run would otherwise lose its lease and be picked up by a
    second worker while the first is still executing it.
    """
    await session.execute(
        update(Submission)
        .where(Submission.id == submission_id, Submission.status == SubmissionStatus.RUNNING)
        .values(lease_expires_at=_now() + timedelta(seconds=lease_seconds))
    )
    await session.commit()


async def requeue(session: AsyncSession, submission_id) -> None:
    """Return a claim without consuming an attempt.

    Used when the worker shut down cleanly mid-run: the work is not at fault, so
    it should not count against ``max_attempts``.
    """
    await session.execute(
        update(Submission)
        .where(Submission.id == submission_id, Submission.status == SubmissionStatus.RUNNING)
        .values(
            status=SubmissionStatus.QUEUED,
            claimed_at=None,
            lease_expires_at=None,
            attempts=Submission.attempts - 1,
        )
    )
    await session.commit()


async def reclaim_expired(session: AsyncSession, *, max_attempts: int = DEFAULT_MAX_ATTEMPTS) -> int:
    """Fail submissions that exhausted their attempts; requeue the rest.

    Returns how many rows were failed. A row that keeps outliving its lease has
    crashed its worker every time, and no amount of retrying will fix it.
    """
    now = _now()
    exhausted = (
        (Submission.status == SubmissionStatus.RUNNING)
        & (Submission.lease_expires_at.is_not(None))
        & (Submission.lease_expires_at < now)
        & (Submission.attempts >= max_attempts)
    )
    result = await session.execute(
        update(Submission)
        .where(exhausted)
        .values(
            status=SubmissionStatus.FAILED,
            finished_at=now,
            error_message="the sandbox did not finish within the retry budget",
        )
    )
    await session.commit()
    return int(result.rowcount or 0)


async def queue_depth(session: AsyncSession) -> dict[str, int]:
    """Queued and running counts, for health output and backpressure."""
    counts: dict[str, int] = {}
    for status in (SubmissionStatus.QUEUED, SubmissionStatus.RUNNING):
        result = await session.execute(
            select(Submission.id).where(Submission.status == status)
        )
        counts[str(status)] = len(result.scalars().all())
    return counts
