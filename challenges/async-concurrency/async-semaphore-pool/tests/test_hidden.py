"""Hidden tests — graded on Submit, never shown to the learner."""

import asyncio
import itertools

import pytest

from solution import run_pool


class Tracker:
    """Records how many jobs are inside their body at the same time."""

    def __init__(self):
        self.active = 0
        self.peak = 0
        self.started = 0

    async def job(self, value):
        self.started += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return value


@pytest.mark.asyncio
async def test_never_exceeds_the_worker_cap():
    tracker = Tracker()
    results = await run_pool([(lambda v=v: tracker.job(v)) for v in range(24)], 3)
    assert results == [(index, index) for index in range(24)]
    assert tracker.peak == 3
    assert tracker.started == 24


@pytest.mark.asyncio
async def test_cap_of_one_serialises_jobs():
    tracker = Tracker()
    await run_pool([(lambda v=v: tracker.job(v)) for v in range(6)], 1)
    assert tracker.peak == 1


@pytest.mark.asyncio
async def test_more_workers_than_jobs():
    tracker = Tracker()
    results = await run_pool([(lambda v=v: tracker.job(v)) for v in range(2)], 10)
    assert results == [(0, 0), (1, 1)]
    assert tracker.peak == 2


@pytest.mark.asyncio
async def test_jobs_are_consumed_lazily():
    produced = []
    tracker = Tracker()

    def job_source():
        for value in itertools.count():
            produced.append(value)
            yield (lambda v=value: tracker.job(v))

    source = job_source()
    results = await run_pool(itertools.islice(source, 7), 2)
    assert results == [(index, index) for index in range(7)]
    assert len(produced) == 7


@pytest.mark.asyncio
async def test_a_failing_job_does_not_cancel_siblings():
    async def flaky(index):
        await asyncio.sleep(0)
        if index == 2:
            raise RuntimeError(f"job {index} failed")
        return index

    results = await run_pool([(lambda i=i: flaky(i)) for i in range(6)], 3)
    assert [index for index, _ in results] == list(range(6))
    for index, outcome in results:
        if index == 2:
            assert isinstance(outcome, RuntimeError)
            assert str(outcome) == "job 2 failed"
        else:
            assert outcome == index


@pytest.mark.asyncio
async def test_generator_source_does_not_stall_on_backpressure():
    async def slow(value):
        await asyncio.sleep(0.002)
        return value

    source = (lambda v=value: slow(v) for value in range(30))
    results = await run_pool(source, 4)
    assert results == [(index, index) for index in range(30)]


@pytest.mark.asyncio
async def test_each_job_callable_is_invoked_exactly_once():
    calls = []

    async def record(value):
        calls.append(value)
        return value

    def make(value):
        def job():
            calls.append(f"invoked-{value}")
            return record(value)

        return job

    await run_pool([make(value) for value in range(5)], 2)
    invoked = [entry for entry in calls if isinstance(entry, str)]
    returned = [entry for entry in calls if isinstance(entry, int)]
    assert sorted(invoked) == [f"invoked-{value}" for value in range(5)]
    assert sorted(returned) == list(range(5))


@pytest.mark.asyncio
async def test_cancellation_propagates():
    started = asyncio.Event()

    async def blocker():
        started.set()
        await asyncio.sleep(30)
        return "never"

    task = asyncio.create_task(run_pool([blocker], 1))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
    except asyncio.TimeoutError:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        pytest.fail("the pool never started the job")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
