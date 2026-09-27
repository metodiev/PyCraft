"""Dashboard, progress, roadmap and skill endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, RepositoryDep, SessionDep
from app.db.base import utcnow
from app.models import Challenge, ChallengeProgress, ProgressStatus, SkillProgress, Submission, User
from app.schemas import (
    ChallengeSummary,
    DashboardResponse,
    ProgressSummary,
    RecentSubmission,
    RoadmapStageSchema,
    SkillBar,
)
from app.services.roadmap import ROADMAP, SKILL_LABELS, level_for_xp, next_level

router = APIRouter(tags=["progress"])

RECENT_LIMIT = 10


@router.get("/dashboard", response_model=DashboardResponse, summary="Full dashboard payload")
async def get_dashboard(
    session: SessionDep, repository: RepositoryDep, user: CurrentUser
) -> DashboardResponse:
    """Everything the dashboard needs in a single round trip."""
    challenges = repository.all()
    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    progress = {row.challenge_id: row for row in progress_rows}

    return DashboardResponse(
        progress=_progress_summary(user, progress, total_challenges=len(challenges)),
        skills=await _skill_bars(session, user, challenges, progress),
        roadmap=_roadmap_view(challenges, progress),
        recent_submissions=await _recent_submissions(session, user),
        recommended_challenge=_recommended(challenges, progress),
        continue_challenge=_in_progress(challenges, progress),
    )


@router.get("/progress", response_model=ProgressSummary, summary="Level and completion summary")
async def get_progress(session: SessionDep, repository: RepositoryDep, user: CurrentUser) -> ProgressSummary:
    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    progress = {row.challenge_id: row for row in progress_rows}
    return _progress_summary(user, progress, total_challenges=len(repository.all()))


@router.get("/roadmap", response_model=list[RoadmapStageSchema], summary="Learning roadmap")
async def get_roadmap(
    session: SessionDep, repository: RepositoryDep, user: CurrentUser
) -> list[RoadmapStageSchema]:
    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    progress = {row.challenge_id: row for row in progress_rows}
    return _roadmap_view(repository.all(), progress)


@router.get("/skills", response_model=list[SkillBar], summary="Skill breakdown")
async def get_skills(
    session: SessionDep, repository: RepositoryDep, user: CurrentUser
) -> list[SkillBar]:
    challenges = repository.all()
    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    progress = {row.challenge_id: row for row in progress_rows}
    return await _skill_bars(session, user, challenges, progress)


# --- builders ------------------------------------------------------------
def _progress_summary(user: User, progress: dict, *, total_challenges: int) -> ProgressSummary:
    completed = sum(
        1 for row in progress.values() if row.status is ProgressStatus.COMPLETED
    )
    level_id, level_label, xp_into = level_for_xp(user.xp)
    upcoming = next_level(user.xp)
    return ProgressSummary(
        xp=user.xp,
        level_id=level_id,
        level_label=level_label,
        xp_into_level=xp_into,
        next_level_label=upcoming[0] if upcoming else None,
        next_level_xp=upcoming[1] if upcoming else None,
        completed_challenges=completed,
        total_challenges=total_challenges,
        completion_pct=round(completed / total_challenges * 100) if total_challenges else 0,
    )


async def _skill_bars(session, user: User, challenges: list, progress: dict) -> list[SkillBar]:
    stored = {
        row.skill: row
        for row in (
            await session.scalars(select(SkillProgress).where(SkillProgress.user_id == user.id))
        ).all()
    }

    totals: dict[str, int] = {}
    completed: dict[str, int] = {}
    for challenge in challenges:
        for skill in challenge.skills:
            totals[skill] = totals.get(skill, 0) + 1
            row = progress.get(challenge.id)
            if row is not None and row.status is ProgressStatus.COMPLETED:
                completed[skill] = completed.get(skill, 0) + 1

    bars: list[SkillBar] = []
    for skill in sorted(set(totals) | set(stored)):
        row = stored.get(skill)
        bars.append(
            SkillBar(
                skill=skill,
                label=SKILL_LABELS.get(skill, skill.replace(".", " ").title()),
                mastery=row.mastery if row else 0,
                xp=row.xp if row else 0,
                challenges_completed=completed.get(skill, 0),
                challenges_total=totals.get(skill, 0),
            )
        )
    # Strongest skills first, matching the dashboard's emphasis on progress.
    bars.sort(key=lambda b: (-b.mastery, b.skill))
    return bars


def _roadmap_view(challenges: list, progress: dict) -> list[RoadmapStageSchema]:
    by_track: dict[str, list] = {}
    for challenge in challenges:
        by_track.setdefault(challenge.track, []).append(challenge)

    stages: list[RoadmapStageSchema] = []
    for stage in ROADMAP:
        track_challenges = by_track.get(stage.id, [])
        completed = sum(
            1
            for c in track_challenges
            if (row := progress.get(c.id)) is not None and row.status is ProgressStatus.COMPLETED
        )
        stages.append(
            RoadmapStageSchema(
                id=stage.id,
                title=stage.title,
                description=stage.description,
                level=stage.level,
                total_challenges=len(track_challenges),
                completed_challenges=completed,
                progress_pct=round(completed / len(track_challenges) * 100)
                if track_challenges
                else 0,
                locked=False,
            )
        )
    return stages


async def _recent_submissions(session, user: User) -> list[RecentSubmission]:
    rows = (
        await session.execute(
            select(Submission, Challenge.title)
            .join(Challenge, Submission.challenge_id == Challenge.id)
            .where(Submission.user_id == user.id)
            .order_by(Submission.created_at.desc())
            .limit(RECENT_LIMIT)
        )
    ).all()

    return [
        RecentSubmission(
            id=submission.id,
            challenge_id=submission.challenge_id,
            challenge_title=title,
            kind=str(submission.kind),
            status=str(submission.status),
            score=submission.score,
            passed=submission.passed,
            failed=submission.failed,
            total_tests=submission.total_tests,
            execution_time_ms=submission.execution_time_ms,
            created_at=submission.created_at,
        )
        for submission, title in rows
    ]


def _recommended(challenges: list, progress: dict) -> ChallengeSummary | None:
    """Next unfinished challenge in roadmap order."""
    for challenge in challenges:
        row = progress.get(challenge.id)
        if row is None or row.status is not ProgressStatus.COMPLETED:
            return _to_summary(challenge, row)
    return None


def _in_progress(challenges: list, progress: dict) -> ChallengeSummary | None:
    """The most recently attempted challenge that is not yet completed."""
    candidates = [
        (c, progress.get(c.id))
        for c in challenges
        if (row := progress.get(c.id)) is not None and row.status is ProgressStatus.IN_PROGRESS
    ]
    if not candidates:
        return None
    challenge, row = max(candidates, key=lambda pair: pair[1].updated_at or utcnow())
    return _to_summary(challenge, row)


def _to_summary(challenge, row: ChallengeProgress | None) -> ChallengeSummary:
    return ChallengeSummary(
        id=challenge.id,
        title=challenge.title,
        summary=challenge.summary,
        difficulty=challenge.difficulty,
        track=challenge.track,
        module=challenge.module,
        level=challenge.level,
        python_version=challenge.python_version,
        points=challenge.points,
        order_index=challenge.order_index,
        skills=challenge.skills,
        tags=challenge.tags,
        visible_test_count=challenge.visible_test_count,
        skill_mastery=row.best_score if row else 0,
        completed=row is not None and row.status is ProgressStatus.COMPLETED,
        best_score=row.best_score if row else 0,
    )
