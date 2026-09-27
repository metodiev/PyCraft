"""The job-processing system: submission, running, results and statistics.

This is the façade the tests drive. It owns no scheduling of its own — that is
``jobqueue.py``'s job — but it does own the bookkeeping: one result per job, the
errors kept where a caller can find them, and the counters that make an async
pipeline observable.

Tests import ``JobSystem`` and ``Stats`` from here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from jobqueue import DeadLetter, Job, JobQueue, JobResult, QueueClosedError
from retry import RetryPolicy

__all__ = [
    "JobSystem",
    "Stats",
    "Job",
    "JobResult",
    "DeadLetter",
    "QueueClosedError",
]

JobFn = Callable[[], Awaitable[Any]]


@dataclass(slots=True)
class Stats:
    """A snapshot of the system's counters.

    ``retries`` counts attempts that were not the job's first, so
    ``attempts == completed + failed + retries``.
    """

    submitted: int = 0
    completed: int = 0
    failed: int = 0
    dead_lettered: int = 0
    attempts: int = 0
    retries: int = 0
    pending: int = 0
    peak_concurrency: int = 0
    closed: bool = False


class JobSystem:
    """Submit named jobs, run them, and read back what happened.

    >>> import asyncio
    >>> async def main():
    ...     async with JobSystem(concurrency=2) as system:
    ...         await system.submit("double", lambda: asyncio.sleep(0, result=42))
    ...         await system.run()
    ...         return system.result("double").value
    >>> asyncio.run(main())
    42
    """

    def __init__(
        self,
        *,
        concurrency: int = 4,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        maxsize: int = 0,
    ) -> None:
        # TODO: build the queue this system delegates to and the bookkeeping it
        # owns: submission order, finished results and the in-flight counter
        # behind ``peak_concurrency``. Do not schedule anything here.
        raise NotImplementedError("Configure JobSystem in __init__")

    # --- submission ------------------------------------------------------
    async def submit(self, name: str, fn: JobFn) -> None:
        """Accept a job called ``name``.

        Names identify results, so they must be unique and non-empty; a closed
        system refuses new work with ``QueueClosedError``. A rejected job must
        not leave a trace in the counters.
        """
        # TODO: validate the name, then delegate to the queue.
        raise NotImplementedError("Implement JobSystem.submit")

    # --- running ---------------------------------------------------------
    async def run(self) -> list[JobResult]:
        """Wait for every accepted job and return all results in job order."""
        # TODO: drain the queue and remember what came back.
        raise NotImplementedError("Implement JobSystem.run")

    async def shutdown(self) -> list[JobResult]:
        """Drain accepted work and refuse anything new."""
        # TODO: shut the queue down and remember what came back.
        raise NotImplementedError("Implement JobSystem.shutdown")

    async def __aenter__(self) -> JobSystem:
        """Enter an ``async with`` block."""
        # TODO: return self.
        raise NotImplementedError("Implement JobSystem.__aenter__")

    async def __aexit__(self, *exc_info: object) -> None:
        """Leave an ``async with`` block, shutting the system down."""
        # TODO: shut down without swallowing the block's exception.
        raise NotImplementedError("Implement JobSystem.__aexit__")

    # --- reading ---------------------------------------------------------
    def ordered_results(self) -> list[JobResult]:
        """Every finished result, in submission order."""
        # TODO: return the finished results in the order they were submitted.
        raise NotImplementedError("Implement JobSystem.ordered_results")

    def result(self, name: str) -> JobResult | None:
        """The result for ``name``, or ``None`` if it has not finished."""
        # TODO: look up one result by name.
        raise NotImplementedError("Implement JobSystem.result")

    @property
    def results(self) -> dict[str, JobResult]:
        """Finished results keyed by job name."""
        # TODO: return a copy so callers cannot mutate the system's state.
        raise NotImplementedError("Implement JobSystem.results")

    @property
    def errors(self) -> dict[str, BaseException]:
        """Only the jobs that ended in an exception, keyed by job name."""
        # TODO: filter the results down to the failures.
        raise NotImplementedError("Implement JobSystem.errors")

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        """Jobs that exhausted their retries."""
        # TODO: delegate to the queue.
        raise NotImplementedError("Implement JobSystem.dead_letters")

    @property
    def pending(self) -> int:
        """Jobs accepted but not yet finished."""
        # TODO: submitted minus finished.
        raise NotImplementedError("Implement JobSystem.pending")

    @property
    def peak_concurrency(self) -> int:
        """The most jobs that were ever in flight at the same time."""
        # TODO: report the observed peak.
        raise NotImplementedError("Implement JobSystem.peak_concurrency")

    @property
    def closed(self) -> bool:
        """True once the system has been shut down."""
        # TODO: delegate to the queue.
        raise NotImplementedError("Implement JobSystem.closed")

    def stats(self) -> Stats:
        """Counters across everything submitted so far.

        ``attempts`` sums every attempt, including the retries of jobs that
        eventually succeeded, so it is the true cost of the run.
        """
        # TODO: build the snapshot. ``attempts == completed + failed + retries``.
        raise NotImplementedError("Implement JobSystem.stats")
