"""The submission queue: claiming, leases, crash recovery and polling.

Run and Submit are asynchronous, so the properties these tests cover are the
ones that keep that safe: two workers must never run one submission, a worker
that dies must not strand its work, and a poller must always reach a terminal
state.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.submission import Submission, SubmissionKind, SubmissionStatus
from app.services import queue
from httpx import AsyncClient
from sqlalchemy import update
from tests.conftest import FakeExecutionBackend, submit_and_wait

CHALLENGE = "python-fundamentals-hello-world"
SOLUTION = {"solution.py": "def greet(name):\n    return f'Hello, {name}!'\n"}


async def seed(factory, user_id, count: int) -> list[uuid.UUID]:
    """Insert ``count`` queued submissions directly, bypassing the API."""
    ids: list[uuid.UUID] = []
    async with factory() as session:
        for index in range(count):
            submission = await queue.enqueue(
                session,
                Submission(
                    user_id=user_id,
                    challenge_id=CHALLENGE,
                    kind=SubmissionKind.RUN,
                    files={"solution.py": f"# {index}"},
                ),
            )
            ids.append(submission.id)
        await session.commit()
    return ids


# --- the endpoints --------------------------------------------------------
@pytest.mark.asyncio
async def test_submit_returns_accepted_rather_than_blocking(client: AsyncClient) -> None:
    """The whole point: the request is not held open for the sandbox run."""
    response = await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["submission_url"].endswith(body["submission_id"])


@pytest.mark.asyncio
async def test_run_returns_accepted_rather_than_blocking(client: AsyncClient) -> None:
    response = await client.post(f"/api/v1/challenges/{CHALLENGE}/run", json={"files": SOLUTION})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_a_queued_submission_reports_not_done(client: AsyncClient) -> None:
    """A poll must be able to tell 'still working' from 'finished'."""
    posted = await client.post(
        f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION}
    )
    submission_id = posted.json()["submission_id"]

    polled = await client.get(f"/api/v1/submissions/{submission_id}")

    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "queued"
    assert body["done"] is False
    assert body["score"] is None


@pytest.mark.asyncio
async def test_polling_a_finished_submission_reports_the_result(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, SOLUTION)

    assert body["done"] is True
    assert body["status"] == "completed"
    assert body["score"] == 100
    assert body["finished_at"] is not None
    assert body["progress"] is not None


@pytest.mark.asyncio
async def test_a_run_poll_reports_output_and_no_score(client: AsyncClient) -> None:
    from tests.conftest import run_and_wait

    body = await run_and_wait(client, CHALLENGE, SOLUTION)

    assert body["done"] is True
    assert "hello from the fake sandbox" in body["stdout"]
    assert body["score"] is None


@pytest.mark.asyncio
async def test_an_unknown_submission_is_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/submissions/{uuid.uuid4()}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_another_learners_submission_is_404_not_403(
    client: AsyncClient, second_client: AsyncClient, anon_client: AsyncClient
) -> None:
    """A 403 would confirm the id exists, which is itself a disclosure."""
    from tests.conftest import register_account

    posted = await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})
    submission_id = posted.json()["submission_id"]

    other = await register_account(anon_client, email="intruder@example.com")
    second_client.headers["Authorization"] = "******" if False else other.headers()["Authorization"]

    response = await second_client.get(f"/api/v1/submissions/{submission_id}")

    assert response.status_code == 404


# --- claiming is atomic ---------------------------------------------------
@pytest.mark.asyncio
async def test_two_workers_never_claim_the_same_submission(
    running_app, account
) -> None:
    """A double claim would run the learner's code twice and double-charge XP."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 1)

    async def claim_once():
        async with factory() as session:
            return await queue.claim(session)

    first, second = await asyncio.gather(claim_once(), claim_once())

    winners = [c for c in (first, second) if c is not None]
    assert len(winners) == 1, "exactly one worker may claim a single row"


@pytest.mark.asyncio
async def test_many_workers_claim_distinct_submissions(running_app, account) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 5)

    async def claim_once():
        async with factory() as session:
            return await queue.claim(session)

    claimed = await asyncio.gather(*[claim_once() for _ in range(5)])

    ids = [c.id for c in claimed if c is not None]
    assert len(ids) == len(set(ids)) == 5


@pytest.mark.asyncio
async def test_claiming_an_empty_queue_returns_none(running_app) -> None:
    from app.db.session import get_session_factory

    async with get_session_factory()() as session:
        assert await queue.claim(session) is None


# --- leases and crash recovery -------------------------------------------
@pytest.mark.asyncio
async def test_a_running_submission_is_not_stolen_while_its_lease_holds(
    running_app, account
) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        first = await queue.claim(session, lease_seconds=600)
    async with factory() as session:
        second = await queue.claim(session)

    assert first is not None
    assert second is None, "a live lease must protect the running submission"


@pytest.mark.asyncio
async def test_an_expired_lease_is_reclaimed(running_app, account) -> None:
    """The worker crashed; the work must not be stranded."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        await queue.claim(session, lease_seconds=0)  # expires immediately
    async with factory() as session:
        reclaimed = await queue.claim(session)

    assert reclaimed is not None


@pytest.mark.asyncio
async def test_a_submission_is_abandoned_after_the_attempt_budget(running_app, account) -> None:
    """A payload that crashes every worker must stop being retried."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    ids = await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        await session.execute(
            update(Submission)
            .where(Submission.id == ids[0])
            .values(
                status=SubmissionStatus.RUNNING,
                attempts=queue.DEFAULT_MAX_ATTEMPTS,
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()

    async with factory() as session:
        assert await queue.claim(session) is None


@pytest.mark.asyncio
async def test_reap_marks_exhausted_submissions_failed(running_app, account) -> None:
    from app.db.session import get_session_factory

    factory = get_session_factory()
    ids = await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        await session.execute(
            update(Submission)
            .where(Submission.id == ids[0])
            .values(
                status=SubmissionStatus.RUNNING,
                attempts=queue.DEFAULT_MAX_ATTEMPTS,
                lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        await session.commit()

    async with factory() as session:
        failed = await queue.reclaim_expired(session)

    assert failed == 1
    async with factory() as session:
        row = await session.get(Submission, ids[0])
        assert row.status is SubmissionStatus.FAILED
        assert row.error_message


@pytest.mark.asyncio
async def test_a_renewed_lease_stays_protected(running_app, account) -> None:
    """A long sandbox run must not lose its claim mid-execution."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        claimed = await queue.claim(session, lease_seconds=1)
    async with factory() as session:
        await queue.renew(session, claimed.id, lease_seconds=600)

    await asyncio.sleep(1.2)  # the original lease would have lapsed by now

    async with factory() as session:
        assert await queue.claim(session) is None


@pytest.mark.asyncio
async def test_requeue_gives_the_attempt_back(running_app, account) -> None:
    """A clean shutdown is not the submission's fault, so it is not charged."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 1)

    async with factory() as session:
        claimed = await queue.claim(session)
    async with factory() as session:
        await queue.requeue(session, claimed.id)
    async with factory() as session:
        again = await queue.claim(session)

    assert again is not None
    assert again.attempts == 1


# --- the worker pool ------------------------------------------------------
@pytest.mark.asyncio
async def test_the_pool_drains_everything_queued(running_app, account) -> None:
    from app.db.session import get_session_factory
    from app.services.workers import WorkerPool

    factory = get_session_factory()
    await seed(factory, uuid.UUID(account.user_id), 4)

    pool = WorkerPool(
        running_app.state.settings,
        running_app.state.execution_backend,
        running_app.state.challenges,
    )
    handled = await pool.run_until_idle()

    assert handled == 4
    async with factory() as session:
        remaining = await queue.queue_depth(session)
    assert sum(remaining.values()) == 0


@pytest.mark.asyncio
async def test_the_pool_records_a_sandbox_failure_as_terminal(
    running_app, account, fake_backend: FakeExecutionBackend
) -> None:
    """A poller must not be left waiting when the sandbox itself fails."""
    from app.db.session import get_session_factory
    from app.execution.models import ExecutionError
    from app.services.workers import WorkerPool

    factory = get_session_factory()
    ids = await seed(factory, uuid.UUID(account.user_id), 1)

    def explode(payload):
        raise ExecutionError("the daemon is unreachable")

    fake_backend.report_factory = explode

    pool = WorkerPool(
        running_app.state.settings,
        running_app.state.execution_backend,
        running_app.state.challenges,
    )
    await pool.run_until_idle()

    async with factory() as session:
        row = await session.get(Submission, ids[0])
        assert row.status is SubmissionStatus.FAILED
        assert "daemon" in (row.error_message or "")


@pytest.mark.asyncio
async def test_the_pool_marks_an_unexpected_crash_as_failed(
    running_app, account, fake_backend: FakeExecutionBackend
) -> None:
    """A bug in grading must still leave the submission terminal."""
    from app.db.session import get_session_factory
    from app.services.workers import WorkerPool

    factory = get_session_factory()
    ids = await seed(factory, uuid.UUID(account.user_id), 1)

    def explode(payload):
        raise RuntimeError("a bug, not a sandbox failure")

    fake_backend.report_factory = explode

    pool = WorkerPool(
        running_app.state.settings,
        running_app.state.execution_backend,
        running_app.state.challenges,
    )
    await pool.run_until_idle()

    async with factory() as session:
        row = await session.get(Submission, ids[0])
        assert row.status is SubmissionStatus.FAILED


@pytest.mark.asyncio
async def test_progress_is_not_touched_by_a_queued_submission(client: AsyncClient) -> None:
    """Enqueueing must not award XP; only actually running the work does."""
    before = (await client.get("/api/v1/progress")).json()

    await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})

    after = (await client.get("/api/v1/progress")).json()
    assert after["completed_challenges"] == before["completed_challenges"]
    assert after["xp"] == before["xp"]


@pytest.mark.asyncio
async def test_queue_depth_counts_waiting_work(client: AsyncClient) -> None:
    await client.post(f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION})

    body = (await client.get("/api/v1/queue")).json()

    assert body["queued"] >= 1
    assert body["depth"] >= 1


@pytest.mark.asyncio
async def test_repeated_polls_of_a_finished_submission_agree(client: AsyncClient) -> None:
    """Polling is not idempotent-by-accident; the result is rebuilt each time."""
    posted = await client.post(
        f"/api/v1/challenges/{CHALLENGE}/submit", json={"files": SOLUTION}
    )
    submission_id = posted.json()["submission_id"]
    await client_drain(client)

    first = (await client.get(f"/api/v1/submissions/{submission_id}")).json()
    second = (await client.get(f"/api/v1/submissions/{submission_id}")).json()

    assert first["score"] == second["score"]
    assert first["total_tests"] == second["total_tests"]
    assert len(first["results"]) == len(second["results"])


async def client_drain(client: AsyncClient) -> int:
    from tests.conftest import drain

    return await drain(client)
