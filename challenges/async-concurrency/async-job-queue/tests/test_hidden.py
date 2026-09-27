"""Hidden tests — the asynchronous details that separate a working queue from
a correct one.

Every test here is deterministic: the retry policy's sleep and random source are
injected, and the concurrency probes coordinate through ``asyncio.Event`` rather
than waiting on a wall clock.
"""

import asyncio
from functools import partial

import pytest

from jobqueue import Job, JobQueue, QueueClosedError
from retry import RetryPolicy
from system import JobSystem

# A correct implementation finishes these in microseconds; the watchdog only
# ever fires for an implementation that has wedged its own event loop, and keeps
# a wedged run from eating the challenge's whole time budget.
WATCHDOG = 1.0


class RecordingSleep:
    """Stands in for ``asyncio.sleep`` and records the delays it was asked for."""

    def __init__(self):
        self.delays = []

    async def __call__(self, delay):
        self.delays.append(delay)


class ScriptedRandom:
    """Deterministic ``random()`` that also counts how often it was consulted."""

    def __init__(self, *values):
        self._values = list(values)
        self.calls = 0

    def random(self):
        self.calls += 1
        return self._values.pop(0) if self._values else 0.5


@pytest.fixture()
def clock():
    return RecordingSleep()


async def _settle(rounds: int = 20):
    """Let every ready task run without consulting the clock."""
    for _ in range(rounds):
        await asyncio.sleep(0)


async def _drain(queue):
    return await asyncio.wait_for(queue.drain(), timeout=WATCHDOG)


async def _echo(value):
    await asyncio.sleep(0)
    return value


async def _stagger(steps):
    for _ in range(steps):
        await asyncio.sleep(0)
    return steps


# --- retry policy --------------------------------------------------------
def test_backoff_is_exponential_not_linear():
    policy = RetryPolicy(max_attempts=6, base_delay=0.25, multiplier=3.0)

    assert [policy.delay_for(n) for n in range(1, 6)] == [0.25, 0.75, 2.25, 6.75, 20.25]


def test_backoff_grows_then_stops_at_the_cap():
    policy = RetryPolicy(max_attempts=8, base_delay=0.1, multiplier=4.0, max_delay=0.5)

    delays = [policy.delay_for(n) for n in range(1, 9)]

    assert delays == [0.1, 0.4, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]


def test_the_cap_is_applied_after_jitter():
    """Capping first lets jitter push the delay back over the limit."""
    rng = ScriptedRandom(*([1.0] * 8))
    policy = RetryPolicy(
        max_attempts=4, base_delay=1.0, multiplier=2.0, max_delay=1.0, jitter=0.5, rng=rng
    )

    delays = [policy.delay_for(n) for n in range(1, 5)]

    assert delays == [1.0, 1.0, 1.0, 1.0]
    assert all(delay <= 1.0 for delay in delays)


def test_jitter_never_produces_a_negative_delay():
    rng = ScriptedRandom(*([0.0] * 8))
    policy = RetryPolicy(max_attempts=4, base_delay=0.1, multiplier=2.0, jitter=1.0, rng=rng)

    delays = [policy.delay_for(n) for n in range(1, 5)]

    assert delays == [0.0, 0.0, 0.0, 0.0]
    assert all(delay >= 0.0 for delay in delays)


def test_jitter_is_drawn_from_the_injected_source():
    """A policy that reaches for the global RNG cannot be made deterministic."""
    rng = ScriptedRandom(1.0)
    policy = RetryPolicy(max_attempts=2, base_delay=1.0, multiplier=1.0, jitter=0.25, rng=rng)

    assert policy.delay_for(1) == 1.25
    assert rng.calls == 1


def test_retry_predicate_marks_some_errors_fatal():
    policy = RetryPolicy(max_attempts=5, retry_on=(TimeoutError, ConnectionError))

    assert policy.should_retry(1, TimeoutError("slow")) is True
    assert policy.should_retry(1, ValueError("bad input")) is False
    assert policy.is_retryable(ValueError("bad input")) is False


def test_callable_predicate_decides_retryability():
    policy = RetryPolicy(max_attempts=5, retry_on=lambda exc: getattr(exc, "transient", False))

    class Transient(Exception):
        transient = True

    class Fatal(Exception):
        transient = False

    assert policy.should_retry(1, Transient()) is True
    assert policy.should_retry(1, Fatal()) is False


def test_cancellation_and_base_exceptions_are_never_retryable():
    policy = RetryPolicy(max_attempts=5)

    assert policy.is_retryable(asyncio.CancelledError()) is False
    assert policy.is_retryable(KeyboardInterrupt()) is False
    assert policy.should_retry(1, asyncio.CancelledError()) is False
    assert policy.is_retryable(RuntimeError("boom")) is True


def test_the_attempt_budget_runs_out_after_max_attempts():
    policy = RetryPolicy(max_attempts=3)

    assert [policy.should_retry(n, RuntimeError()) for n in (1, 2, 3, 4)] == [
        True,
        True,
        False,
        False,
    ]


def test_rejects_degenerate_attempt_numbers_and_limits():
    policy = RetryPolicy()

    with pytest.raises(ValueError):
        policy.delay_for(0)
    with pytest.raises(ValueError):
        policy.should_retry(0, RuntimeError())
    with pytest.raises(ValueError):
        RetryPolicy(base_delay=-0.1)
    with pytest.raises(ValueError):
        RetryPolicy(max_delay=-0.1)
    for bad_jitter in (-0.1, 1.5):
        with pytest.raises(ValueError):
            RetryPolicy(jitter=bad_jitter)


# --- job queue -----------------------------------------------------------
@pytest.mark.asyncio
async def test_the_concurrency_cap_is_never_exceeded():
    """A semaphore released early — or never acquired — shows up right here."""
    queue = JobQueue(concurrency=3, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()
    started = 0
    active = 0
    peak = 0

    async def gated():
        nonlocal started, active, peak
        started += 1
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
            return "done"
        finally:
            active -= 1

    async def scenario():
        for index in range(12):
            await queue.submit(Job(f"job-{index}", gated))
        await _settle()
        assert started == 3, "exactly `concurrency` jobs may be in flight"
        assert peak == 3
        release.set()
        return await queue.drain()

    results = await asyncio.wait_for(scenario(), timeout=WATCHDOG)

    assert [result.value for result in results] == ["done"] * 12
    assert peak == 3


@pytest.mark.asyncio
async def test_a_cap_of_one_serialises_every_job():
    queue = JobQueue(concurrency=1, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()
    active = 0
    peak = 0
    started = 0

    async def gated():
        nonlocal active, peak, started
        started += 1
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
            return "done"
        finally:
            active -= 1

    async def scenario():
        for index in range(5):
            await queue.submit(Job(f"job-{index}", gated))
        await _settle()
        assert started == 1
        release.set()
        return await queue.drain()

    results = await asyncio.wait_for(scenario(), timeout=WATCHDOG)

    assert [result.value for result in results] == ["done"] * 5
    assert peak == 1


@pytest.mark.asyncio
async def test_jobs_accepted_while_busy_are_not_lost():
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()
    finished = []

    async def gated(name):
        await release.wait()
        finished.append(name)
        return name

    await queue.submit(Job("first", partial(gated, "first")))
    await queue.submit(Job("second", partial(gated, "second")))
    await _settle()
    assert finished == []

    for index in range(4):
        await queue.submit(Job(f"late-{index}", partial(gated, f"late-{index}")))
    await _settle()
    assert finished == [], "jobs must not finish before the gate opens"

    release.set()
    results = await _drain(queue)

    assert [result.id for result in results] == [
        "first",
        "second",
        "late-0",
        "late-1",
        "late-2",
        "late-3",
    ]
    assert sorted(finished) == [
        "first",
        "late-0",
        "late-1",
        "late-2",
        "late-3",
        "second",
    ]


@pytest.mark.asyncio
async def test_a_failing_job_does_not_kill_its_worker(clock):
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=2, base_delay=0.01), sleep=clock)

    async def doomed():
        raise TimeoutError("always down")

    await queue.submit(Job("doomed", doomed))
    for index in range(6):
        await queue.submit(Job(f"ok-{index}", partial(_echo, index)))

    results = await _drain(queue)

    assert [result.id for result in results] == ["doomed"] + [f"ok-{index}" for index in range(6)]
    assert isinstance(results[0].error, TimeoutError)
    assert [result.value for result in results[1:]] == list(range(6))
    assert all(result.ok for result in results[1:])


@pytest.mark.asyncio
async def test_drain_returns_results_in_submission_order():
    queue = JobQueue(concurrency=4, policy=RetryPolicy(max_attempts=1))

    for value in (5, 0, 4, 1, 3, 2):
        await queue.submit(Job(f"job-{value}", partial(_stagger, value)))

    results = await _drain(queue)

    assert [result.id for result in results] == [f"job-{value}" for value in (5, 0, 4, 1, 3, 2)]
    assert [result.value for result in results] == [5, 0, 4, 1, 3, 2]
    assert [result.attempts for result in results] == [1] * 6


@pytest.mark.asyncio
async def test_retry_delays_grow_exponentially_then_stop_at_the_cap(clock):
    policy = RetryPolicy(max_attempts=6, base_delay=0.1, multiplier=2.0, max_delay=0.5)
    queue = JobQueue(concurrency=1, policy=policy, sleep=clock)
    calls = []

    async def always_fails():
        calls.append(1)
        raise TimeoutError("down")

    await queue.submit(Job("flaky", always_fails))
    results = await _drain(queue)

    assert len(calls) == 6
    assert clock.delays == [0.1, 0.2, 0.4, 0.5, 0.5]
    assert results[0].attempts == 6


@pytest.mark.asyncio
async def test_exhausted_jobs_are_dead_lettered_exactly_once(clock):
    queue = JobQueue(concurrency=1, policy=RetryPolicy(max_attempts=3, base_delay=0.01), sleep=clock)
    calls = []

    async def always_fails():
        calls.append(1)
        raise TimeoutError("down")

    await queue.submit(Job("doomed", always_fails))
    results = await _drain(queue)
    await _settle()

    assert len(calls) == 3, "a dead-lettered job must not be retried forever"
    assert len(results) == 1, "one result per job, not one per attempt"
    assert results[0].attempts == 3
    assert isinstance(results[0].error, TimeoutError)
    assert len(queue.dead_letters) == 1
    assert queue.dead_letters[0].id == "doomed"
    assert queue.dead_letters[0].attempts == 3
    assert isinstance(queue.dead_letters[0].error, TimeoutError)
    assert len(clock.delays) == 2


@pytest.mark.asyncio
async def test_a_fatal_error_is_not_retried_and_not_dead_lettered(clock):
    policy = RetryPolicy(max_attempts=4, base_delay=0.01, retry_on=(TimeoutError,))
    queue = JobQueue(concurrency=1, policy=policy, sleep=clock)
    calls = []

    async def fatal():
        calls.append(1)
        raise ValueError("bad payload")

    await queue.submit(Job("fatal", fatal))
    results = await _drain(queue)

    assert len(calls) == 1
    assert clock.delays == []
    assert queue.dead_letters == ()
    assert results[0].attempts == 1
    assert isinstance(results[0].error, ValueError)


@pytest.mark.asyncio
async def test_a_retried_job_yields_one_result_carrying_its_total_attempts(clock):
    policy = RetryPolicy(max_attempts=3, base_delay=0.02, multiplier=2.0, retry_on=(TimeoutError,))
    queue = JobQueue(concurrency=2, policy=policy, sleep=clock)
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("warming up")
        return "ok"

    await queue.submit(Job("flaky", flaky))
    await queue.submit(Job("steady", partial(_echo, "steady")))
    results = await _drain(queue)

    assert [result.id for result in results] == ["flaky", "steady"]
    assert results[0].ok is True
    assert results[0].value == "ok"
    assert results[0].attempts == 3
    assert results[1].value == "steady"
    assert results[1].attempts == 1
    assert len(calls) == 3
    assert clock.delays == [0.02, 0.04]


@pytest.mark.asyncio
async def test_pending_counts_accepted_but_unfinished_jobs():
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()

    async def gated():
        await release.wait()
        return "done"

    for index in range(5):
        await queue.submit(Job(f"job-{index}", gated))
    await _settle()

    assert queue.pending == 5
    release.set()
    await _drain(queue)
    assert queue.pending == 0


@pytest.mark.asyncio
async def test_shutdown_drains_every_accepted_job():
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=1))

    for index in range(7):
        await queue.submit(Job(f"job-{index}", partial(_echo, index)))

    results = await asyncio.wait_for(queue.shutdown(), timeout=WATCHDOG)

    assert [result.value for result in results] == list(range(7))
    assert queue.closed is True
    with pytest.raises(QueueClosedError):
        await queue.submit(Job("late", partial(_echo, 8)))


@pytest.mark.asyncio
async def test_shutdown_waits_for_in_flight_jobs_instead_of_cancelling_them():
    queue = JobQueue(concurrency=2, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()
    finished = []

    async def gated():
        await release.wait()
        finished.append("finished")
        return "ok"

    await queue.submit(Job("a", gated))
    await queue.submit(Job("b", gated))
    await _settle()

    shutdown = asyncio.create_task(queue.shutdown())
    await _settle()
    assert not shutdown.done(), "shutdown must wait for accepted work"

    release.set()
    results = await asyncio.wait_for(shutdown, timeout=WATCHDOG)

    assert [result.value for result in results] == ["ok", "ok"]
    assert finished == ["finished", "finished"]


@pytest.mark.asyncio
async def test_a_bounded_queue_pushes_back_on_its_producer():
    """``maxsize`` is what stops a producer from outrunning its workers."""
    queue = JobQueue(concurrency=1, policy=RetryPolicy(max_attempts=1), maxsize=2)
    release = asyncio.Event()
    started = []

    async def gated(name):
        started.append(name)
        await release.wait()
        return name

    async def scenario():
        await queue.submit(Job("a", partial(gated, "a")))
        await _settle()
        assert started == ["a"], "the single worker must pick up the first job"

        await queue.submit(Job("b", partial(gated, "b")))
        await queue.submit(Job("c", partial(gated, "c")))

        blocked = asyncio.create_task(queue.submit(Job("d", partial(gated, "d"))))
        await _settle()
        assert not blocked.done(), "a full queue must make submit wait"

        release.set()
        await blocked
        return await queue.drain()

    results = await asyncio.wait_for(scenario(), timeout=WATCHDOG)

    assert [result.id for result in results] == ["a", "b", "c", "d"]
    assert [result.value for result in results] == ["a", "b", "c", "d"]


@pytest.mark.asyncio
async def test_draining_an_idle_queue_is_immediate():
    queue = JobQueue(concurrency=3)

    assert await _drain(queue) == []
    assert queue.pending == 0
    assert queue.closed is False
    assert await asyncio.wait_for(queue.shutdown(), timeout=WATCHDOG) == []
    assert queue.closed is True


def test_the_queue_rejects_degenerate_limits():
    with pytest.raises(ValueError):
        JobQueue(concurrency=0)
    with pytest.raises(ValueError):
        JobQueue(concurrency=-1)
    with pytest.raises(ValueError):
        JobQueue(maxsize=-1)


# --- system --------------------------------------------------------------
@pytest.mark.asyncio
async def test_results_are_recorded_once_per_job_not_once_per_attempt(clock):
    policy = RetryPolicy(max_attempts=3, base_delay=0.01, retry_on=(TimeoutError,))
    system = JobSystem(concurrency=2, policy=policy, sleep=clock)
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("not yet")
        return "ok"

    await system.submit("flaky", flaky)
    await system.submit("steady", partial(_echo, "steady"))
    results = await system.run()

    assert [result.id for result in results] == ["flaky", "steady"]
    assert len(system.results) == 2
    assert system.result("flaky").attempts == 3
    assert system.result("missing") is None

    stats = system.stats()
    assert stats.submitted == 2
    assert stats.completed == 2
    assert stats.failed == 0
    assert stats.attempts == 4
    assert stats.retries == 2
    assert stats.pending == 0
    assert stats.dead_lettered == 0
    assert clock.delays == [0.01, 0.02]


@pytest.mark.asyncio
async def test_errors_are_captured_per_job_and_never_escape(clock):
    policy = RetryPolicy(max_attempts=2, base_delay=0.01, retry_on=(TimeoutError,))
    system = JobSystem(concurrency=3, policy=policy, sleep=clock)

    async def doomed():
        raise TimeoutError("down")

    async def fatal():
        raise ValueError("bad")

    await system.submit("doomed", doomed)
    await system.submit("fatal", fatal)
    await system.submit("fine", partial(_echo, 1))
    results = await system.run()

    assert [result.id for result in results] == ["doomed", "fatal", "fine"]
    assert set(system.errors) == {"doomed", "fatal"}
    assert isinstance(system.errors["doomed"], TimeoutError)
    assert isinstance(system.errors["fatal"], ValueError)
    assert system.results["fine"].ok is True
    assert [entry.id for entry in system.dead_letters] == ["doomed"]

    stats = system.stats()
    assert stats.failed == 2
    assert stats.completed == 1
    assert stats.dead_lettered == 1


@pytest.mark.asyncio
async def test_peak_concurrency_never_exceeds_the_cap():
    system = JobSystem(concurrency=3, policy=RetryPolicy(max_attempts=1))
    release = asyncio.Event()
    active = 0
    peak = 0

    async def gated():
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await release.wait()
            return "ok"
        finally:
            active -= 1

    async def scenario():
        for index in range(9):
            await system.submit(f"job-{index}", gated)
        await _settle()
        assert system.peak_concurrency == 3
        release.set()
        return await system.run()

    results = await asyncio.wait_for(scenario(), timeout=WATCHDOG)

    assert [result.value for result in results] == ["ok"] * 9
    assert peak == 3
    assert system.stats().peak_concurrency == 3


@pytest.mark.asyncio
async def test_run_preserves_submission_order_when_the_first_job_is_slowest():
    system = JobSystem(concurrency=4, policy=RetryPolicy(max_attempts=1))

    for value in (6, 0, 5, 1, 4, 2, 3):
        await system.submit(f"job-{value}", partial(_stagger, value))

    results = await system.run()

    assert [result.id for result in results] == [f"job-{value}" for value in (6, 0, 5, 1, 4, 2, 3)]
    assert [result.value for result in results] == [6, 0, 5, 1, 4, 2, 3]


@pytest.mark.asyncio
async def test_shutdown_returns_every_result_and_closes_the_system():
    system = JobSystem(concurrency=2, policy=RetryPolicy(max_attempts=1))

    for index in range(5):
        await system.submit(f"job-{index}", partial(_echo, index))

    results = await asyncio.wait_for(system.shutdown(), timeout=WATCHDOG)

    assert [result.value for result in results] == list(range(5))
    assert system.closed is True
    assert system.pending == 0
    assert system.stats().closed is True


@pytest.mark.asyncio
async def test_the_context_manager_shuts_the_system_down():
    async with JobSystem(concurrency=2, policy=RetryPolicy(max_attempts=1)) as system:
        for index in range(3):
            await system.submit(f"job-{index}", partial(_echo, index))
        assert system.closed is False

    assert system.closed is True
    assert [result.value for result in system.ordered_results()] == [0, 1, 2]
    with pytest.raises(QueueClosedError):
        await system.submit("late", partial(_echo, 9))


@pytest.mark.asyncio
async def test_job_names_must_be_unique_and_non_empty():
    system = JobSystem(concurrency=1, policy=RetryPolicy(max_attempts=1))

    with pytest.raises(ValueError):
        await system.submit("", partial(_echo, 1))

    await system.submit("dup", partial(_echo, 1))
    with pytest.raises(ValueError):
        await system.submit("dup", partial(_echo, 2))

    assert system.stats().submitted == 1
    await system.run()
    assert [result.value for result in system.ordered_results()] == [1]


def test_the_system_reexports_the_queue_vocabulary():
    import system as system_module

    from jobqueue import DeadLetter, Job, JobResult

    assert system_module.Job is Job
    assert system_module.JobResult is JobResult
    assert system_module.DeadLetter is DeadLetter
    assert system_module.QueueClosedError is QueueClosedError
