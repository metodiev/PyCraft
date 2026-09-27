"""Achievement catalogue and evaluation.

Achievements are **definitions in code** plus **unlock rows in the database**.
That split means adding an achievement needs no migration, and re-evaluating
every user is cheap.

An achievement is a predicate over a :class:`LearnerSnapshot` — a value object
built once per evaluation. Adding one is a single ``Achievement(...)`` entry
below; nothing else needs to change.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AchievementCategory,
    AchievementTier,
    ChallengeProgress,
    ProgressStatus,
    SkillProgress,
    Submission,
    User,
    UserAchievement,
)
from app.services.roadmap import ROADMAP

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Achievement:
    """One unlockable achievement."""

    key: str
    name: str
    description: str
    category: AchievementCategory
    tier: AchievementTier
    # Points awarded on top of challenge XP.
    bonus_xp: int = 0
    # Predicate over the learner's snapshot.
    check: Callable[[LearnerSnapshot], bool] = lambda _snapshot: False
    # Optional human-readable progress, e.g. (3, 10) for "3 of 10".
    progress: Callable[[LearnerSnapshot], tuple[int, int]] | None = None


@dataclass(slots=True)
class LearnerSnapshot:
    """Everything an achievement predicate may inspect.

    Built with a bounded number of queries, so evaluation never becomes an N+1
    problem as the catalogue grows.
    """

    user: User
    completed_challenges: int = 0
    total_challenges: int = 0
    perfect_scores: int = 0
    passed_by_difficulty: dict[str, int] = field(default_factory=dict)
    # Completed challenges grouped by track, so roadmap stages can be tested.
    completed_by_track: dict[str, int] = field(default_factory=dict)
    totals_by_track: dict[str, int] = field(default_factory=dict)
    skills_mastered: int = 0
    highest_skill_mastery: int = 0
    total_attempts: int = 0
    submissions_last_24h: int = 0
    current_streak: int = 0
    longest_streak: int = 0

    @property
    def completion_pct(self) -> int:
        if self.total_challenges == 0:
            return 0
        return round(self.completed_challenges / self.total_challenges * 100)

    def completed_in_tracks(self, tracks: Iterable[str]) -> bool:
        """True when every given track that *has content* is fully complete.

        A track that has not shipped yet must not block the achievement — but it
        must not satisfy it either. If none of the named tracks have any content
        the answer is ``False``, otherwise a "complete track X" achievement
        would unlock the moment a learner solved anything at all.
        """
        tracks_with_content = 0
        for track in tracks:
            total = self.totals_by_track.get(track, 0)
            if total == 0:
                continue
            tracks_with_content += 1
            if self.completed_by_track.get(track, 0) < total:
                return False
        return tracks_with_content > 0


# --- the catalogue -------------------------------------------------------
# Ordered roughly by the journey a learner takes.
ACHIEVEMENTS: tuple[Achievement, ...] = (
    Achievement(
        key="first-steps",
        name="First Steps",
        description="Solve your first challenge.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.BRONZE,
        bonus_xp=10,
        check=lambda s: s.completed_challenges >= 1,
        progress=lambda s: (min(s.completed_challenges, 1), 1),
    ),
    Achievement(
        key="foundations",
        name="Foundations Laid",
        description="Complete every Python Fundamentals challenge.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.SILVER,
        bonus_xp=75,
        check=lambda s: s.completed_in_tracks(("python-fundamentals",)),
    ),
    Achievement(
        key="professional-python",
        name="Professional Grade",
        description="Complete every Professional Python challenge.",
        category=AchievementCategory.SKILL,
        tier=AchievementTier.SILVER,
        bonus_xp=100,
        check=lambda s: s.completed_in_tracks(("python-professional",)),
    ),
    Achievement(
        key="five-solved",
        name="Getting Somewhere",
        description="Solve 5 challenges.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.BRONZE,
        bonus_xp=50,
        check=lambda s: s.completed_challenges >= 5,
        progress=lambda s: (min(s.completed_challenges, 5), 5),
    ),
    Achievement(
        key="ten-solved",
        name="Committed",
        description="Solve 10 challenges.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.SILVER,
        bonus_xp=150,
        check=lambda s: s.completed_challenges >= 10,
        progress=lambda s: (min(s.completed_challenges, 10), 10),
    ),
    Achievement(
        key="quarter-of-the-way",
        name="Quarter of the Way",
        description="Reach 25% completion of the roadmap.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.SILVER,
        bonus_xp=100,
        check=lambda s: s.total_challenges >= 4 and s.completion_pct >= 25,
        progress=lambda s: (min(s.completion_pct, 25), 25),
    ),
    Achievement(
        key="halfway",
        name="Halfway There",
        description="Reach 50% completion of the roadmap.",
        category=AchievementCategory.PROGRESS,
        tier=AchievementTier.GOLD,
        bonus_xp=250,
        check=lambda s: s.total_challenges >= 4 and s.completion_pct >= 50,
        progress=lambda s: (min(s.completion_pct, 50), 50),
    ),
    Achievement(
        key="perfect-first-try",
        name="Flawless",
        description="Score 100 on a challenge.",
        category=AchievementCategory.EXCELLENCE,
        tier=AchievementTier.SILVER,
        bonus_xp=75,
        check=lambda s: s.perfect_scores >= 1,
    ),
    Achievement(
        key="perfectionist",
        name="Perfectionist",
        description="Score 100 on 5 challenges.",
        category=AchievementCategory.EXCELLENCE,
        tier=AchievementTier.GOLD,
        bonus_xp=200,
        check=lambda s: s.perfect_scores >= 5,
        progress=lambda s: (min(s.perfect_scores, 5), 5),
    ),
    Achievement(
        key="advanced-solver",
        name="Into the Deep End",
        description="Solve an advanced challenge.",
        category=AchievementCategory.SKILL,
        tier=AchievementTier.GOLD,
        bonus_xp=150,
        check=lambda s: s.passed_by_difficulty.get("advanced", 0) >= 1,
    ),
    Achievement(
        key="expert-solver",
        name="Expert Territory",
        description="Solve an expert challenge.",
        category=AchievementCategory.SKILL,
        tier=AchievementTier.PLATINUM,
        bonus_xp=300,
        check=lambda s: s.passed_by_difficulty.get("expert", 0) >= 1,
    ),
    Achievement(
        key="skill-mastery",
        name="Mastery",
        description="Reach 100% mastery in any skill.",
        category=AchievementCategory.SKILL,
        tier=AchievementTier.GOLD,
        bonus_xp=150,
        check=lambda s: s.highest_skill_mastery >= 100,
    ),
    Achievement(
        key="well-rounded",
        name="Well Rounded",
        description="Demonstrate 5 different skills.",
        category=AchievementCategory.SKILL,
        tier=AchievementTier.SILVER,
        bonus_xp=125,
        check=lambda s: s.skills_mastered >= 5,
        progress=lambda s: (min(s.skills_mastered, 5), 5),
    ),
    Achievement(
        key="persistent",
        name="Persistent",
        description="Make 25 submission attempts.",
        category=AchievementCategory.EXCELLENCE,
        tier=AchievementTier.BRONZE,
        bonus_xp=50,
        check=lambda s: s.total_attempts >= 25,
        progress=lambda s: (min(s.total_attempts, 25), 25),
    ),
    Achievement(
        key="streak-3",
        name="Building Momentum",
        description="Solve challenges 3 days in a row.",
        category=AchievementCategory.CONSISTENCY,
        tier=AchievementTier.BRONZE,
        bonus_xp=50,
        check=lambda s: s.longest_streak >= 3,
        progress=lambda s: (min(s.longest_streak, 3), 3),
    ),
    Achievement(
        key="streak-7",
        name="Consistent",
        description="Solve challenges 7 days in a row.",
        category=AchievementCategory.CONSISTENCY,
        tier=AchievementTier.SILVER,
        bonus_xp=150,
        check=lambda s: s.longest_streak >= 7,
        progress=lambda s: (min(s.longest_streak, 7), 7),
    ),
    Achievement(
        key="streak-30",
        name="Relentless",
        description="Solve challenges 30 days in a row.",
        category=AchievementCategory.CONSISTENCY,
        tier=AchievementTier.PLATINUM,
        bonus_xp=500,
        check=lambda s: s.longest_streak >= 30,
        progress=lambda s: (min(s.longest_streak, 30), 30),
    ),
    Achievement(
        key="prolific",
        name="Prolific",
        description="Make 20 submissions in a single day.",
        category=AchievementCategory.EXCELLENCE,
        tier=AchievementTier.SILVER,
        bonus_xp=100,
        check=lambda s: s.submissions_last_24h >= 20,
    ),
    Achievement(
        key="explorer",
        name="Explorer",
        description="Attempt challenges in 3 different tracks.",
        category=AchievementCategory.EXPLORATION,
        tier=AchievementTier.SILVER,
        bonus_xp=100,
        check=lambda s: len([t for t, n in s.completed_by_track.items() if n > 0]) >= 3,
    ),
)


# Track ids that must all be complete for the capstone achievement.
_ROADMAP_TRACKS = tuple(stage.id for stage in ROADMAP)

# The capstone is defined separately because it depends on the roadmap, then
# merged in so there is a single ordered catalogue.
_CAPSTONE = Achievement(
    key="roadmap-complete",
    name="Roadmap Complete",
    description="Complete every challenge across the whole roadmap.",
    category=AchievementCategory.PROGRESS,
    tier=AchievementTier.PLATINUM,
    bonus_xp=1000,
    check=lambda s: s.total_challenges >= 10
    and s.completion_pct >= 100
    and s.completed_in_tracks(_ROADMAP_TRACKS),
)

ACHIEVEMENTS: tuple[Achievement, ...] = (*ACHIEVEMENTS, _CAPSTONE)
ACHIEVEMENTS_BY_KEY: dict[str, Achievement] = {a.key: a for a in ACHIEVEMENTS}


# --- evaluation ----------------------------------------------------------
async def build_snapshot(
    session: AsyncSession, user: User, *, challenge_index: dict[str, object]
) -> LearnerSnapshot:
    """Collect everything achievement predicates need, in a few queries.

    ``challenge_index`` maps challenge id -> LoadedChallenge so difficulty and
    track live in memory rather than requiring a join per row.
    """
    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    completed_ids = {
        row.challenge_id for row in progress_rows if row.status is ProgressStatus.COMPLETED
    }

    passed_by_difficulty: dict[str, int] = {}
    completed_by_track: dict[str, int] = {}
    totals_by_track: dict[str, int] = {}
    for challenge_id, challenge in challenge_index.items():
        track = getattr(challenge, "track", "unknown")
        totals_by_track[track] = totals_by_track.get(track, 0) + 1
        if challenge_id in completed_ids:
            completed_by_track[track] = completed_by_track.get(track, 0) + 1
            difficulty = getattr(challenge, "difficulty", "beginner")
            passed_by_difficulty[difficulty] = passed_by_difficulty.get(difficulty, 0) + 1

    perfect_scores = sum(1 for row in progress_rows if row.best_score >= 100)
    total_attempts = sum(row.attempts for row in progress_rows)

    skills = (
        await session.scalars(
            select(SkillProgress).where(SkillProgress.user_id == user.id)
        )
    ).all()
    skills_mastered = sum(1 for row in skills if row.mastery >= 60)
    highest_mastery = max((row.mastery for row in skills), default=0)

    since = datetime.now(UTC) - timedelta(hours=24)
    recent = await session.scalar(
        select(func.count())
        .select_from(Submission)
        .where(Submission.user_id == user.id, Submission.created_at >= since)
    )

    return LearnerSnapshot(
        user=user,
        completed_challenges=len(completed_ids),
        total_challenges=len(challenge_index),
        perfect_scores=perfect_scores,
        passed_by_difficulty=passed_by_difficulty,
        completed_by_track=completed_by_track,
        totals_by_track=totals_by_track,
        skills_mastered=skills_mastered,
        highest_skill_mastery=highest_mastery,
        total_attempts=total_attempts,
        submissions_last_24h=int(recent or 0),
        # Column defaults are applied by the database, so an unflushed row reads
        # as None rather than 0.
        current_streak=int(user.current_streak or 0),
        longest_streak=int(user.longest_streak or 0),
    )


async def evaluate_and_unlock(
    session: AsyncSession,
    user: User,
    *,
    challenge_index: dict[str, object],
    context: dict[str, object] | None = None,
) -> list[Achievement]:
    """Unlock any newly earned achievements. Returns the ones just unlocked.

    Called after a graded submission. Only ever inserts rows, so it is safe to
    call repeatedly — the unique index on (user, key) makes it idempotent.
    """
    snapshot = await build_snapshot(session, user, challenge_index=challenge_index)

    already = set(
        await session.scalars(
            select(UserAchievement.achievement_key).where(UserAchievement.user_id == user.id)
        )
    )

    newly_unlocked: list[Achievement] = []
    bonus_xp = 0
    for achievement in ACHIEVEMENTS:
        if achievement.key in already:
            continue
        try:
            if not achievement.check(snapshot):
                continue
        except Exception:
            logger.exception("Achievement %s raised during evaluation", achievement.key)
            continue

        session.add(
            UserAchievement(
                user_id=user.id,
                achievement_key=achievement.key,
                unlocked_at=datetime.now(UTC),
                context=dict(context or {}),
            )
        )
        newly_unlocked.append(achievement)
        bonus_xp += achievement.bonus_xp

    if bonus_xp:
        user.xp += bonus_xp
    if newly_unlocked:
        await session.flush()
        logger.info(
            "Unlocked %d achievement(s) for %s (+%d XP)",
            len(newly_unlocked),
            user.email,
            bonus_xp,
        )
    return newly_unlocked


async def list_unlocked(session: AsyncSession, user_id) -> dict[str, UserAchievement]:
    rows = await session.scalars(
        select(UserAchievement).where(UserAchievement.user_id == user_id)
    )
    return {row.achievement_key: row for row in rows}


def unlocked_out(achievement: Achievement, *, unlocked_at: datetime | None = None) -> dict[str, object]:
    """Describe a freshly unlocked achievement for an immediate API response.

    Takes the definition directly rather than a database row, so a submission
    result can report unlocks without awaiting a round trip.
    """
    return {
        "key": achievement.key,
        "name": achievement.name,
        "description": achievement.description,
        "category": str(achievement.category),
        "tier": str(achievement.tier),
        "bonus_xp": achievement.bonus_xp,
        "unlocked": True,
        "unlocked_at": unlocked_at or datetime.now(UTC),
        "progress": None,
    }


def achievement_view(row: UserAchievement) -> dict[str, object]:
    """Merge a stored unlock with its definition for API responses."""
    definition = ACHIEVEMENTS_BY_KEY.get(row.achievement_key)
    if definition is None:
        return {
            "key": row.achievement_key,
            "name": row.achievement_key,
            "description": "",
            "category": "progress",
            "tier": "bronze",
            "bonus_xp": 0,
            "unlocked": True,
            "unlocked_at": row.unlocked_at,
            "progress": None,
        }
    return unlocked_out(definition, unlocked_at=row.unlocked_at)


def locked_view(achievement: Achievement, snapshot: LearnerSnapshot | None) -> dict[str, object]:
    """Describe a not-yet-earned achievement, with progress when available."""
    progress: tuple[int, int] | None = None
    if snapshot is not None and achievement.progress is not None:
        try:
            progress = achievement.progress(snapshot)
        except Exception:
            progress = None

    return {
        "key": achievement.key,
        "name": achievement.name,
        "description": achievement.description,
        "category": str(achievement.category),
        "tier": str(achievement.tier),
        "bonus_xp": achievement.bonus_xp,
        "unlocked": False,
        "unlocked_at": None,
        "progress": {"current": progress[0], "target": progress[1]} if progress else None,
    }
