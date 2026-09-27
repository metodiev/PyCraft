"""Submission orchestration: load content, build payload, execute, grade, persist."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.execution.base import ExecutionBackend
from app.execution.models import (
    ExecutionError,
    ExecutionLimits,
    ExecutionMode,
    ExecutionPayload,
    ExecutionReport,
    ExecutionStatus,
    TestOutcome,
    TestResult,
)
from app.models import ChallengeProgress, ProgressStatus, SkillProgress, Submission, User
from app.models.submission import SubmissionKind, SubmissionStatus
from app.services import queue
from app.services.challenges import ChallengeRepository, LoadedChallenge
from app.services.roadmap import level_for_xp
from app.services.scoring import score_submission

logger = logging.getLogger(__name__)


class SubmissionService:
    """Coordinates a single Run or Submit request."""

    def __init__(
        self,
        session: AsyncSession,
        backend: ExecutionBackend,
        repository: ChallengeRepository,
        settings: Settings,
    ) -> None:
        self._session = session
        self._backend = backend
        self._repository = repository
        self._settings = settings

    # --- public API ------------------------------------------------------
    async def enqueue(
        self, user_id, challenge_id: str, files: dict[str, str], mode: ExecutionMode
    ) -> Submission:
        """Validate and persist a submission as runnable work.

        Returns as soon as the row exists: nothing executes here, so the request
        that called this is never held open by the sandbox.
        """
        challenge = self._repository.get(challenge_id)
        submission = Submission(
            user_id=user_id,
            challenge_id=challenge.id,
            kind=SubmissionKind.SUBMIT if mode is ExecutionMode.SUBMIT else SubmissionKind.RUN,
            files=files,
        )
        await queue.enqueue(self._session, submission)
        await self._session.commit()
        return submission

    async def process(self, submission_id) -> Submission:
        """Execute a claimed submission and record the outcome.

        This is the worker path. The row must already be claimed; the caller owns
        the lease. Grading and progress are applied here, not at enqueue time, so
        a submission that never runs cannot advance anyone's progress.
        """
        submission = await self._session.get(Submission, submission_id)
        if submission is None:  # pragma: no cover - the worker only passes live ids
            raise LookupError(f"submission {submission_id} disappeared")

        challenge = self._repository.get(submission.challenge_id)
        mode = (
            ExecutionMode.SUBMIT
            if submission.kind is SubmissionKind.SUBMIT
            else ExecutionMode.RUN
        )
        payload = self._build_payload(challenge, submission.files, mode)

        try:
            report = await self._backend.execute(payload)
        except ExecutionError as exc:
            # Infrastructure failure: record it on the row so a poller sees a
            # terminal state rather than waiting forever for a worker that died.
            logger.warning("Execution failed for submission %s: %s", submission.id, exc)
            submission.status = SubmissionStatus.FAILED
            submission.error_message = str(exc)
            submission.finished_at = _utcnow()
            await self._session.commit()
            raise

        self._apply_report(submission, report, mode)
        await self._touch_progress(submission.user_id, challenge, submission)

        if mode is ExecutionMode.SUBMIT:
            scoring = self._grade(submission, report)
            unlocked = await self._record_progress(submission.user_id, submission, scoring)
            from app.services.achievements import unlocked_out

            # ``unlocked_out`` returns a datetime for the HTTP response; JSON
            # storage needs it as text, so serialise before persisting.
            submission.unlocked = [_jsonable(unlocked_out(entry)) for entry in unlocked]

        submission.finished_at = _utcnow()
        await self._session.commit()
        return submission

    async def outcome(self, submission: Submission) -> dict:
        """The grading detail a caller needs to render a finished Submit.

        Rebuilt from the stored row rather than cached, so polling a completed
        submission returns the same answer long after the worker is gone.
        """
        challenge = self._repository.get(submission.challenge_id)
        # Tests keep their own hidden flag from the original run, so the
        # hidden/visible split survives the round trip through storage.
        report = ExecutionReport(
            status=ExecutionStatus(submission.status),
            tests=[TestResult.from_dict(item) for item in (submission.results or [])],
            stdout=submission.stdout,
            stderr=submission.stderr,
            exit_code=submission.exit_code,
            execution_time_ms=submission.execution_time_ms or 0,
            memory_used_mb=submission.memory_used_mb or 0.0,
            error_message=submission.error_message,
        )
        hidden_tests = [t for t in report.tests if t.hidden]
        hidden_total = len(hidden_tests)
        hidden_passed = sum(1 for t in hidden_tests if t.status is TestOutcome.PASSED)

        scoring = score_submission(
            report,
            difficulty=challenge.difficulty,
            source="\n".join(submission.files.values()),
            time_limit_ms=challenge.time_limit_ms,
            hidden_total=hidden_total,
            hidden_passed=hidden_passed,
        )
        return {"scoring": scoring, "report": report}

    async def progress_snapshot(self, user_id) -> dict:
        return await self._progress_snapshot(user_id)

    # --- payload ---------------------------------------------------------
    def _build_payload(
        self, challenge: LoadedChallenge, files: dict[str, str], mode: ExecutionMode
    ) -> ExecutionPayload:
        """Assemble the sandbox payload.

        A single-file challenge names its entry ``solution.py`` so tests can
        always ``from solution import ...``. A project keeps its own structure
        and ships every starter file the learner did not override, so an
        unmodified helper still resolves at import time.
        """
        if not challenge.is_project:
            normalised = dict(files)
            if challenge.entry_file in normalised and challenge.entry_file != "solution.py":
                normalised["solution.py"] = normalised.pop(challenge.entry_file)
            return ExecutionPayload(
                files=normalised,
                tests=challenge.files.visible_tests,
                hidden_tests=challenge.files.hidden_tests,
                entry_file="solution.py",
                limits=ExecutionLimits(
                    time_limit_ms=challenge.time_limit_ms,
                    memory_limit_mb=challenge.memory_limit_mb,
                ),
                mode=mode,
                python_version=challenge.python_version,
                include_hidden=mode is ExecutionMode.SUBMIT,
            )

        merged: dict[str, str] = dict(challenge.files.starter_files)
        for name, source in files.items():
            # A learner may add new modules, but may not shadow the tests.
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            merged[name] = source

        return ExecutionPayload(
            files=merged,
            tests=challenge.files.visible_tests,
            hidden_tests=challenge.files.hidden_tests,
            entry_file=challenge.entry_file,
            limits=ExecutionLimits(
                time_limit_ms=challenge.time_limit_ms,
                memory_limit_mb=challenge.memory_limit_mb,
            ),
            mode=mode,
            python_version=challenge.python_version,
            include_hidden=mode is ExecutionMode.SUBMIT,
        )

    def _apply_report(
        self, submission: Submission, report: ExecutionReport, mode: ExecutionMode
    ) -> None:
        hidden_stems: set[str] = set()
        if mode is ExecutionMode.SUBMIT:
            challenge = self._repository.get(submission.challenge_id)
            hidden_stems = {name.removesuffix(".py") for name in challenge.files.hidden_tests}

        results: list[TestResult] = []
        for test in report.tests:
            test.hidden = _is_hidden(test, hidden_stems)
            results.append(test)

        submission.status = _map_status(report)
        submission.passed = report.passed
        submission.failed = report.failed
        submission.total_tests = report.total
        submission.execution_time_ms = report.execution_time_ms
        submission.memory_used_mb = report.memory_used_mb
        submission.exit_code = report.exit_code
        submission.results = [t.to_dict() for t in results]

        if mode is ExecutionMode.RUN:
            # Run is for experimentation: the learner needs their own output to
            # debug. Hidden tests are absent, so nothing graded can leak.
            submission.stdout = report.stdout
            submission.stderr = report.stderr
        else:
            # Submit applies hidden tests that are materialised in the sandbox
            # next to the learner's code. Withholding raw output keeps that
            # suite from being read back through prints.
            submission.stdout = ""
            submission.stderr = ""
            submission.error_message = report.error_message

    # --- grading & progress ----------------------------------------------
    def _grade(self, submission: Submission, report: ExecutionReport):
        challenge = self._repository.get(submission.challenge_id)
        # Count actual hidden *tests*, not hidden files: one hidden module can
        # contain many tests, and the split must match the report exactly.
        hidden_tests = [t for t in report.tests if t.hidden]
        hidden_total = len(hidden_tests)
        hidden_passed = sum(1 for t in hidden_tests if t.status is TestOutcome.PASSED)
        source = "\n".join(submission.files.values())

        scoring = score_submission(
            report,
            difficulty=challenge.difficulty,
            source=source,
            time_limit_ms=challenge.time_limit_ms,
            hidden_total=hidden_total,
            hidden_passed=hidden_passed,
        )
        submission.score = scoring.score
        return scoring

    async def _touch_progress(self, user_id, challenge: LoadedChallenge, submission: Submission) -> None:
        """Ensure a progress row exists and the attempt counter stays current.

        Scoring happens after this runs, so ``best_score`` is owned solely by
        :meth:`_record_progress`.

        The row is flushed, not merely added: ``_record_progress`` looks it up by
        ``(user_id, challenge_id)``, and an unflushed insert is invisible to that
        query — which would make the second call insert a duplicate row and trip
        the unique constraint.
        """
        progress = await self._get_progress(user_id, challenge.id)
        if progress is None:
            progress = ChallengeProgress(
                user_id=user_id,
                challenge_id=challenge.id,
                status=ProgressStatus.IN_PROGRESS,
                attempts=0,
                best_score=0,
            )
            self._session.add(progress)
        progress.attempts += 1
        await self._session.flush()

    async def _record_progress(self, user_id, submission: Submission, scoring) -> list:
        """Update completion, XP, skills, streak and achievements after a Submit.

        Returns any achievements unlocked by this submission.
        """
        challenge = self._repository.get(submission.challenge_id)
        progress = await self._get_progress(user_id, challenge.id)
        if progress is None:  # pragma: no cover - _touch_progress always creates it
            progress = ChallengeProgress(
                user_id=user_id,
                challenge_id=challenge.id,
                attempts=0,
                best_score=0,
            )
            self._session.add(progress)

        # ``submission.score`` was set by _grade(), which runs after the row was
        # created but before this method.
        if submission.score is not None:
            progress.best_score = max(progress.best_score, submission.score)

        newly_completed = False
        if scoring.passed and progress.status is not ProgressStatus.COMPLETED:
            progress.status = ProgressStatus.COMPLETED
            progress.completed_at = _utcnow()
            newly_completed = True

        await self._update_skills(user_id, challenge, scoring.score)

        if newly_completed:
            await self._record_activity(user_id)
            await self._award_xp(user_id, challenge.points)

        await self._session.flush()
        unlocked = await self._unlock_achievements(user_id, challenge.id)
        await self._session.commit()
        return unlocked

    async def _record_activity(self, user_id) -> None:
        """Advance the learner's streak for a genuine solve."""
        from app.services.streaks import register_activity

        user = await self._session.get(User, user_id)
        if user is not None:
            register_activity(user, _today())

    async def _unlock_achievements(self, user_id, challenge_id: str) -> list:
        """Evaluate achievements after a solve and return any newly unlocked."""
        from app.services.achievements import evaluate_and_unlock

        user = await self._session.get(User, user_id)
        if user is None:  # pragma: no cover - the user always exists here
            return []
        challenge_index = {c.id: c for c in self._repository.all()}
        return await evaluate_and_unlock(
            self._session,
            user,
            challenge_index=challenge_index,
            context={"challenge_id": challenge_id},
        )

    async def _award_xp(self, user_id, points: int) -> None:
        user = await self._session.get(User, user_id)
        if user is not None:
            user.xp += points

    async def _update_skills(self, user_id, challenge: LoadedChallenge, score: int) -> None:
        for skill in challenge.skills:
            row = await self._session.scalar(
                select(SkillProgress).where(
                    SkillProgress.user_id == user_id, SkillProgress.skill == skill
                )
            )
            if row is None:
                row = SkillProgress(user_id=user_id, skill=skill, xp=0, mastery=0)
                self._session.add(row)
            row.xp += max(1, score // 10) if score >= 60 else score // 20
            row.mastery = min(100, max(row.mastery, score))
        await self._session.flush()

    async def _get_progress(self, user_id, challenge_id: str) -> ChallengeProgress | None:
        return await self._session.scalar(
            select(ChallengeProgress).where(
                ChallengeProgress.user_id == user_id,
                ChallengeProgress.challenge_id == challenge_id,
            )
        )

    async def _progress_snapshot(self, user_id) -> dict:
        user = await self._session.get(User, user_id)
        xp = user.xp if user else 0
        level_id, level_label, xp_into = level_for_xp(xp)

        rows = (
            await self._session.scalars(
                select(ChallengeProgress).where(ChallengeProgress.user_id == user_id)
            )
        ).all()
        completed = sum(1 for r in rows if r.status is ProgressStatus.COMPLETED)
        total = len(self._repository.all())

        from app.services.roadmap import next_level

        upcoming = next_level(xp)
        return {
            "xp": xp,
            "level_id": level_id,
            "level_label": level_label,
            "xp_into_level": xp_into,
            "next_level_label": upcoming[0] if upcoming else None,
            "next_level_xp": upcoming[1] if upcoming else None,
            "completed_challenges": completed,
            "total_challenges": total,
            "completion_pct": round(completed / total * 100) if total else 0,
        }


def _is_hidden(test: TestResult, hidden_stems: set[str]) -> bool:
    """A test is hidden when it came from a hidden test module.

    Test names arrive as ``<module>.py::<test>``; the module stem is what
    distinguishes the graded suite from the visible one.
    """
    if not hidden_stems:
        return False
    module = test.name.split("::", 1)[0].removesuffix(".py")
    return module in hidden_stems


def _map_status(report: ExecutionReport) -> SubmissionStatus:
    if report.status is ExecutionStatus.TIMEOUT:
        return SubmissionStatus.COMPLETED  # graded as zero, but the run itself finished
    if report.status is ExecutionStatus.COMPLETED:
        return SubmissionStatus.COMPLETED
    if report.status is ExecutionStatus.REJECTED:
        return SubmissionStatus.REJECTED
    return SubmissionStatus.FAILED


def _jsonable(value):
    """Recursively convert a value into something a JSON column can store.

    ``unlocked_out`` builds an HTTP-shaped payload that includes a ``datetime``;
    the column is JSON, so dates must become ISO strings or the insert fails at
    flush time.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _utcnow():
    return datetime.now(UTC)


def _today():
    return datetime.now(UTC).date()
