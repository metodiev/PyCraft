"""Visible tests — the basic contract for each module."""

import asyncio

import pytest

from jobqueue import Job, JobQueue, QueueClosedError
from retry import RetryPolicy
from system import JobSystem


class FakeClock:
    """Records the delays a caller asked for instead of sleeping for real."""

    def __init__(self):
        self.delays = []

    async def sleep(self, delay):
        self.delays.append(delay)


@pytest.fixture()
def clock():
    return FakeClock()


# --- retry policy --------------------------------------------------------
def test_delay_grows_geometrically():
    policy = RetryPolicy(max_attempts=5, base_delay=0.1, multiplier=2.0)

    assert [policy.delay_for(n) for n in (1, 2, 3)] == [0.1, 0.2, 0.4]


def test_should_retry_stops_at_max_attempts():
    policy = RetryPolicy(max_attempts=2)

    assert policy.should_retry(1, ValueError("x")) is True
    assert policy.should_retry(2, ValueError("x")) is False


def test_retry_predicate_can_call_an_error_fatal():
    policy = RetryPolicy(max_attempts=5, retry_on=lambda exc: isinstance(exc, TimeoutError))

    assert policy.should_retry(1, TimeoutError("slow")) is True
    assert policy.should_retry(1, ValueError("bad input")) is False


def test_rejects_invalid_configuration():
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(multiplier=0.5)


# --- job queue -----------------------------------------------------------
@pytest.mark.asyncio
async def test_queue_runs_a_job_and_returns_its_value():
    queue = JobQueue(concurrency=2)

    async def work():
        return "done"

    await queue.submit(Job("a", work))
    results = await queue.drain()

    assert [result.value for result in results] == ["done"]
    assert results[0].ok is True


@pytest.mark.asyncio
async def test_queue_records_an_error_without_raising():
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=1))

    async def boom():
        raise ValueError("nope")

    await queue.submit(Job("bad", boom))
    results = await queue.drain()

    assert isinstance(results[0].error, ValueError)
    assert results[0].ok is False


@pytest.mark.asyncio
async def test_retryable_job_is_retried_until_it_succeeds(clock):
    queue = JobQueue(
        concurrency=1,
        policy=RetryPolicy(max_attempts=3, base_delay=0.01),
        sleep=clock.sleep,
    )
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("not yet")
        return "finally"

    await queue.submit(Job("flaky", flaky))
    results = await queue.drain()

    assert results[0].value == "finally"
    assert results[0].attempts == 3
    assert len(clock.delays) == 2


@pytest.mark.asyncio
async def test_shutdown_rejects_new_work():
    queue = JobQueue(concurrency=1)
    await queue.shutdown()

    with pytest.raises(QueueClosedError):
        await queue.submit(Job("late", lambda: asyncio.sleep(0)))


# --- system --------------------------------------------------------------
@pytest.mark.asyncio
async def test_system_returns_results_in_submission_order():
    system = JobSystem(concurrency=2, policy=RetryPolicy(max_attempts=1))

    for index in range(4):
        await system.submit(f"job-{index}", (lambda value=index: asyncio.sleep(0, result=value)))

    results = await system.run()

    assert [result.id for result in results] == [f"job-{index}" for index in range(4)]
    assert [result.value for result in results] == [0, 1, 2, 3]


@pytest.mark.asyncio
async def test_system_captures_errors_per_job():
    system = JobSystem(concurrency=2, policy=RetryPolicy(max_attempts=1))

    async def boom():
        raise RuntimeError("exploded")

    await system.submit("good", lambda: asyncio.sleep(0, result=1))
    await system.submit("bad", boom)
    await system.run()

    assert system.result("good").value == 1
    assert isinstance(system.errors["bad"], RuntimeError)
    assert "good" not in system.errors


@pytest.mark.asyncio
async def test_system_reports_stats():
    system = JobSystem(concurrency=1, policy=RetryPolicy(max_attempts=1))
    await system.submit("a", lambda: asyncio.sleep(0, result=1))
    await system.run()

    stats = system.stats()
    assert stats.submitted == 1
    assert stats.completed == 1
    assert stats.pending == 0
