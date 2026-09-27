"""Schemas for achievements, streaks and leaderboards."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class AchievementProgressValue(BaseModel):
    current: int
    target: int


class AchievementOut(BaseModel):
    key: str
    name: str
    description: str
    category: str
    tier: str
    bonus_xp: int = 0
    unlocked: bool
    unlocked_at: datetime | None = None
    # Only present for locked achievements that can express progress.
    progress: AchievementProgressValue | None = None


class AchievementProgress(BaseModel):
    earned: list[AchievementOut] = Field(default_factory=list)
    locked: list[AchievementOut] = Field(default_factory=list)
    total: int
    earned_count: int


class StreakOut(BaseModel):
    current: int
    longest: int
    last_active_date: date | None = None
    active_today: bool = False
    # False when the streak lapsed; `current` is then 0.
    alive: bool = False


class LeaderboardEntry(BaseModel):
    """A public leaderboard row.

    Deliberately excludes email and account id beyond a stable uuid, so the
    leaderboard cannot be used to enumerate users.
    """

    rank: int
    user_id: uuid.UUID
    display_name: str
    avatar_url: str = ""
    level_label: str
    xp: int
    completed_challenges: int
    streak: int = 0
    is_you: bool = False


class SubmissionOutcomeAchievements(BaseModel):
    """Achievements unlocked by a submission, surfaced in the result payload."""

    newly_unlocked: list[AchievementOut] = Field(default_factory=list)
    bonus_xp: int = 0
