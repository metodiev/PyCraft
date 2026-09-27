"""A bounded async job queue backed by a pool of workers.

This module owns *scheduling*: the concurrency cap, completion, retries and the
dead-letter queue. It must not depend on ``system.py``.

``sleep`` is injectable so retry tests never wait for a real clock — the
sandbox's retry tests take milliseconds, not seconds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from retry import RetryPolicy

__all__ = ["QueueClosedError", "Job", "JobResult", "DeadLetter", "JobQueue"]

JobFn = Callable[[], Awaitable[Any]]


class QueueClosedError(RuntimeError):
    """Raised when work is submitted to a queue that has been shut down."""


@dataclass(slots=True)
class Job:
    """One unit of work: an id and a callable returning a coroutine."""

    id: str
    run: JobFn


@dataclass(slots=True)
class JobResult:
    """The outcome of one job — exactly one per submitted job, not per attempt."""

    id: str
    value: Any = None
    error: BaseException | None = None
    attempts: int = 1

    @property
    def ok(self) -> bool:
        """True when the job finished without an exception."""
        return self.error is None


@dataclass(slots=True)
class DeadLetter:
    """A job that kept failing until its retryable attempts ran out."""

    id: str
    error: BaseException
    attempts: int


class JobQueue:
    """Runs submitted jobs with at most ``concurrency`` of them in flight.

    >>> import asyncio
    >>> async def main():
    ...     queue = JobQueue(concurrency=2)
    ...     await queue.submit(Job("a", lambda: asyncio.sleep(0, result=1)))
    ...     return [result.value for result in await queue.shutdown()]
    >>> asyncio.run(main())
    [1]
    """

    def __init__(
        self,
        *,
        concurrency: int = 4,
        policy: RetryPolicy | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        maxsize: int = 0,
    ) -> None:
        # TODO: accept the configuration and build the state you need — a queue,
        # worker tasks, the per-job results keyed by submission order, the
        # dead-letter list, and the counters behind ``pending``.
        # Reject a concurrency below 1 and a negative ``maxsize``. Default
        # ``sleep`` to ``asyncio.sleep`` and ``policy`` to ``RetryPolicy()``.
        raise NotImplementedError("Configure JobQueue in __init__")

    # --- inspection ------------------------------------------------------
    @property
    def concurrency(self) -> int:
        """The hard cap on jobs running at the same time."""
        return self._concurrency

    @property
    def policy(self) -> RetryPolicy:
        """The retry policy this queue applies."""
        return self._policy

    @property
    def closed(self) -> bool:
        """True once :meth:`shutdown` has been called."""
        # TODO: report whether the queue accepts new work.
        raise NotImplementedError("Implement JobQueue.closed")

    @property
    def pending(self) -> int:
        """Accepted jobs that have not produced a result yet."""
        # TODO: submitted jobs minus finished ones.
        raise NotImplementedError("Implement JobQueue.pending")

    @property
    def dead_letters(self) -> tuple[DeadLetter, ...]:
        """Jobs that exhausted their retries, in the order they gave up."""
        # TODO: return the dead letters as an immutable sequence.
        raise NotImplementedError("Implement JobQueue.dead_letters")

    # --- submission ------------------------------------------------------
    async def submit(self, job: Job) -> None:
        """Accept ``job`` for execution.

        Blocks while the queue is full (``maxsize``), which is the backpressure
        that stops a producer from outrunning its workers. A closed queue
        refuses work with ``QueueClosedError``.
        """
        # TODO: refuse when closed, start the workers on first use, and hand the
        # job to them. Do not run the job here — submission only accepts work.
        raise NotImplementedError("Implement JobQueue.submit")

    # --- completion ------------------------------------------------------
    async def drain(self) -> list[JobResult]:
        """Wait for every accepted job, then return the results in job order."""
        # TODO: wait for the accepted work and return one result per job, in
        # submission order. Nothing may be left running when this returns.
        raise NotImplementedError("Implement JobQueue.drain")

    async def shutdown(self) -> list[JobResult]:
        """Drain accepted work, then refuse anything new.

        Closing happens *before* the drain so a job submitted while we wait
        cannot extend the work this call promises to finish.
        """
        # TODO: mark closed, drain, then stop the workers. Accepted work must
        # complete — cancelling it is not a graceful shutdown.
        raise NotImplementedError("Implement JobQueue.shutdown")
