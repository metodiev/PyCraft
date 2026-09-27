"""Background workers that drain the submission queue.

A worker owns no state of its own: it claims a row, executes it, writes the
result, and loops. Everything it needs is in the database, which is what makes
the queue survivable — a worker can be killed between any two steps and another
one will pick the work up once the lease expires.

The API process runs these by default so a single-container deployment keeps
working, and they are the reason a submission no longer blocks an HTTP request.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import Settings
from app.execution.base import ExecutionBackend, ExecutionError
from app.services.challenges import ChallengeRepository
from app.services.queue import claim, reclaim_expired, renew
from app.services.submissions import SubmissionService

logger = logging.getLogger(__name__)

#: How often an idle worker looks for work. Short enough that a submission
#: starts promptly, long enough that an idle platform is not a busy loop.
POLL_INTERVAL_SECONDS = 0.25

#: How often to sweep for submissions whose worker died.
REAP_INTERVAL_SECONDS = 30.0


class WorkerPool:
    """A fixed set of workers draining the submission queue."""

    def __init__(
        self,
        settings: Settings,
        backend: ExecutionBackend,
        repository: ChallengeRepository,
        *,
        workers: int | None = None,
        session_factory=None,
    ) -> None:
        self._settings = settings
        self._backend = backend
        self._repository = repository
        self._count = max(1, workers if workers is not None else settings.worker_concurrency)
        self._session_factory = session_factory
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = asyncio.Event()
        #: Set once a worker has claimed and finished at least one submission.
        #: Tests and the health endpoint use this to know the pool is live.
        self.processed = 0

    @property
    def worker_count(self) -> int:
        """How many workers this pool runs."""
        return self._count

    # --- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        if self._tasks:
            return
        self._stopping.clear()
        self._tasks = [
            asyncio.create_task(self._run(index), name=f"pycraft-worker-{index}")
            for index in range(self._count)
        ]
        logger.info("Submission workers started (count=%d)", self._count)

    async def stop(self) -> None:
        """Signal workers to stop and wait for the in-flight run to finish.

        A worker checks the stop flag between submissions, never during one, so
        a graceful shutdown does not abandon a learner mid-execution.
        """
        self._stopping.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        logger.info("Submission workers stopped")

    # --- worker loop -----------------------------------------------------
    async def run_until_idle(self, *, max_iterations: int = 500) -> int:
        """Process every runnable submission, then return.

        Used by tests, which need the real claim/execute/persist path without
        depending on wall-clock timing. Production drains through the
        background workers instead.
        """
        factory = self._session_factory or _default_factory()
        handled = 0
        for _ in range(max_iterations):
            if not await self._drain_one(factory):
                break
            handled += 1
        return handled

    async def _run(self, index: int) -> None:
        factory = self._session_factory or _default_factory()
        reaped_at = 0.0
        while not self._stopping.is_set():
            try:
                if await self._drain_one(factory):
                    continue  # work may be waiting; do not sleep
                # Nothing to do: occasionally sweep for abandoned claims.
                loop_time = asyncio.get_running_loop().time()
                if loop_time - reaped_at > REAP_INTERVAL_SECONDS:
                    reaped_at = loop_time
                    async with factory() as session:
                        failed = await reclaim_expired(session)
                    if failed:
                        logger.warning("Abandoned %d submission(s) past the retry budget", failed)
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A worker must never die silently: log it and keep draining.
                logger.exception("Worker %d hit an unexpected error; continuing", index)
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _drain_one(self, factory) -> bool:
        """Process a single submission. Returns whether one was handled."""
        async with factory() as session:
            submission = await claim(session, lease_seconds=self._settings.worker_lease_seconds)
            if submission is None:
                return False
            submission_id = submission.id

        async with factory() as session:
            service = SubmissionService(session, self._backend, self._repository, self._settings)
            heartbeat = asyncio.create_task(self._keep_alive(factory, submission_id))
            try:
                await service.process(submission_id)
                self.processed += 1
            except ExecutionError:
                # ``process`` already recorded the failure on the row; the
                # worker simply moves on.
                logger.info("Submission %s failed in the sandbox", submission_id)
            except LookupError:
                logger.warning("Submission %s vanished before it could run", submission_id)
            except Exception:
                # Anything else is a bug in grading or persistence. Mark the row
                # failed so a poller is not left waiting forever.
                logger.exception("Submission %s failed while processing", submission_id)
                await self._mark_failed(factory, submission_id)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
        return True

    async def _keep_alive(self, factory, submission_id) -> None:
        """Renew the lease while a long submission runs.

        Without this a sandbox run longer than the lease would be picked up by
        another worker and executed twice.
        """
        interval = max(1.0, self._settings.worker_lease_seconds / 3)
        while True:
            await asyncio.sleep(interval)
            try:
                async with factory() as session:
                    await renew(
                        session, submission_id, lease_seconds=self._settings.worker_lease_seconds
                    )
            except Exception:
                # A lost heartbeat must not kill the run.
                logger.warning("Could not renew the lease for %s", submission_id)

    async def _mark_failed(self, factory, submission_id) -> None:
        from app.models.submission import Submission, SubmissionStatus

        async with factory() as session:
            row = await session.get(Submission, submission_id)
            if row is not None and not SubmissionStatus(row.status).is_terminal:
                row.status = SubmissionStatus.FAILED
                row.error_message = "the worker could not complete this submission"
                await session.commit()


def _default_factory():
    from app.db.session import get_session_factory

    return get_session_factory()
