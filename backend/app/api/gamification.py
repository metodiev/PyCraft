"""Gamification API: achievements, streaks and leaderboards."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, OptionalUser, RepositoryDep, SessionDep
from app.models import ChallengeProgress, ProgressStatus, User
from app.schemas.gamification import (
    AchievementOut,
    AchievementProgress,
    LeaderboardEntry,
    StreakOut,
)
from app.services.achievements import (
    ACHIEVEMENTS,
    achievement_view,
    build_snapshot,
    list_unlocked,
    locked_view,
)
from app.services.roadmap import level_for_xp
from app.services.streaks import effective_streak, streak_is_alive

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gamification"])

LEADERBOARD_LIMIT = 50


@router.get(
    "/achievements",
    response_model=AchievementProgress,
    summary="Achievements earned and still locked",
)
async def get_achievements(
    session: SessionDep, repository: RepositoryDep, user: CurrentUser
) -> AchievementProgress:
    """Every achievement, with the learner's progress towards the locked ones."""
    unlocked_rows = await list_unlocked(session, user.id)
    challenge_index = {c.id: c for c in repository.all()}
    snapshot = await build_snapshot(session, user, challenge_index=challenge_index)

    earned: list[AchievementOut] = [
        AchievementOut(**achievement_view(row)) for row in unlocked_rows.values()
    ]
    locked: list[AchievementOut] = [
        AchievementOut(**locked_view(achievement, snapshot))
        for achievement in ACHIEVEMENTS
        if achievement.key not in unlocked_rows
    ]

    earned.sort(key=lambda a: a.unlocked_at or datetime.min.replace(tzinfo=UTC), reverse=True)

    return AchievementProgress(
        earned=earned,
        locked=locked,
        total=len(ACHIEVEMENTS),
        earned_count=len(earned),
    )


@router.get("/streak", response_model=StreakOut, summary="Current and longest streak")
async def get_streak(session: SessionDep, user: CurrentUser) -> StreakOut:
    today = _today()
    return StreakOut(
        current=effective_streak(user, today),
        longest=user.longest_streak,
        last_active_date=user.last_active_date,
        active_today=user.last_active_date == today,
        alive=streak_is_alive(user, today),
    )


@router.get(
    "/leaderboard",
    response_model=list[LeaderboardEntry],
    summary="Top learners by XP",
)
async def get_leaderboard(
    session: SessionDep,
    user: OptionalUser,
    limit: int = Query(default=20, ge=1, le=LEADERBOARD_LIMIT),
) -> list[LeaderboardEntry]:
    """Ranked by XP.

    Only non-sensitive fields are exposed: a leaderboard must not become a way
    to harvest email addresses.
    """
    solved = func.count(ChallengeProgress.id).label("solved")
    rows = (
        await session.execute(
            select(User, solved)
            .outerjoin(
                ChallengeProgress,
                (ChallengeProgress.user_id == User.id)
                & (ChallengeProgress.status == ProgressStatus.COMPLETED),
            )
            .where(User.is_active.is_(True), User.xp > 0)
            .group_by(User.id)
            .order_by(User.xp.desc(), User.created_at.asc())
            .limit(limit)
        )
    ).all()

    return [
        LeaderboardEntry(
            rank=index,
            user_id=row_user.id,
            display_name=row_user.display_name,
            avatar_url=row_user.avatar_url,
            level_label=level_for_xp(row_user.xp)[1],
            xp=row_user.xp,
            completed_challenges=int(solved_count),
            streak=effective_streak(row_user, _today()),
            is_you=user is not None and row_user.id == user.id,
        )
        for index, (row_user, solved_count) in enumerate(rows, start=1)
    ]


@router.get("/leaderboard/me", response_model=LeaderboardEntry | None, summary="Your rank")
async def get_my_rank(session: SessionDep, user: CurrentUser) -> LeaderboardEntry | None:
    """The caller's position, even when outside the top N."""
    solved = func.count(ChallengeProgress.id).label("solved")
    rows = (
        await session.execute(
            select(User, solved)
            .outerjoin(
                ChallengeProgress,
                (ChallengeProgress.user_id == User.id)
                & (ChallengeProgress.status == ProgressStatus.COMPLETED),
            )
            .where(User.is_active.is_(True), User.xp > 0)
            .group_by(User.id)
            .order_by(User.xp.desc(), User.created_at.asc())
        )
    ).all()

    for index, (row_user, solved_count) in enumerate(rows, start=1):
        if row_user.id == user.id:
            return LeaderboardEntry(
                rank=index,
                user_id=row_user.id,
                display_name=row_user.display_name,
                avatar_url=row_user.avatar_url,
                level_label=level_for_xp(row_user.xp)[1],
                xp=row_user.xp,
                completed_challenges=int(solved_count),
                streak=effective_streak(row_user, _today()),
                is_you=True,
            )
    return None


def _today() -> date:
    return datetime.now(UTC).date()
