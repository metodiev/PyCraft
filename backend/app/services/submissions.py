"""Submission orchestration: load content, build payload, execute, grade, persist."""

from __future__ import annotations

import logging

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
from app.models import ChallengeProgress, ProgressStatus, SkillProgress, Submission
from app.models.submission import SubmissionKind, SubmissionStatus
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
    async def run(self, user_id, challenge_id: str, files: dict[str, str]) -> tuple[Submission, ExecutionReport]:
        return await self._execute(user_id, challenge_id, files, ExecutionMode.RUN)

    async def submit(
        self, user_id, challenge_id: str, files: dict[str, str]
    ) -> tuple[Submission, ExecutionReport, dict]:
        submission, report = await self._execute(user_id, challenge_id, files, ExecutionMode.SUBMIT)
        scoring = self._grade(submission, report)
        await self._record_progress(user_id, submission, scoring)
        progress = await self._progress_snapshot(user_id)
        return submission, report, {"scoring": scoring, "progress": progress}

    # --- execution -------------------------------------------------------
    async def _execute(
        self,
        user_id,
        challenge_id: str,
        files: dict[str, str],
        mode: ExecutionMode,
    ) -> tuple[Submission, ExecutionReport]:
        challenge = self._repository.get(challenge_id)

        submission = Submission(
            user_id=user_id,
            challenge_id=challenge.id,
            kind=SubmissionKind.SUBMIT if mode is ExecutionMode.SUBMIT else SubmissionKind.RUN,
            status=SubmissionStatus.QUEUED,
            files=files,
        )
        self._session.add(submission)
        await self._session.flush()

        payload = self._build_payload(challenge, files, mode)

        try:
            report = await self._backend.execute(payload)
        except ExecutionError as exc:
            logger.warning("Execution failed for submission %s: %s", submission.id, exc)
            submission.status = SubmissionStatus.FAILED
            submission.error_message = str(exc)
            await self._session.commit()
            raise

        self._apply_report(submission, report, mode)
        await self._touch_progress(user_id, challenge, submission)
        await self._session.commit()
        await self._session.refresh(submission)
        return submission, report

    def _build_payload(
        self, challenge: LoadedChallenge, files: dict[str, str], mode: ExecutionMode
    ) -> ExecutionPayload:
        # The starter's entry filename is normalised so tests can always
        # ``from solution import ...`` regardless of what the author named it.
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

    async def _record_progress(self, user_id, submission: Submission, scoring) -> None:
        """Update completion status, XP and skill mastery after a Submit."""
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

        if scoring.passed and progress.status is not ProgressStatus.COMPLETED:
            progress.status = ProgressStatus.COMPLETED
            progress.completed_at = _utcnow()
            await self._award_xp(user_id, challenge.points)

        await self._update_skills(user_id, challenge, scoring.score)
        await self._session.commit()

    async def _award_xp(self, user_id, points: int) -> None:
        from app.models import User

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
        from app.models import User

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


def _utcnow():
    from datetime import UTC, datetime

    return datetime.now(UTC)
