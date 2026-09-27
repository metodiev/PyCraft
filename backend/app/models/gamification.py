"""Gamification: achievements, badges and streaks.

Achievement *definitions* are code (they need logic to evaluate); *unlocks* are
rows. That split means adding an achievement is a pure addition with no
migration, and re-evaluating them for every user is cheap.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class AchievementTier(enum.StrEnum):
    """Rarity, which drives the badge colour in the UI."""

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class AchievementCategory(enum.StrEnum):
    PROGRESS = "progress"
    SKILL = "skill"
    CONSISTENCY = "consistency"
    EXCELLENCE = "excellence"
    EXPLORATION = "exploration"


class UserAchievement(Base, TimestampMixin):
    """An achievement unlocked by a user.

    ``context`` records what triggered the unlock (the challenge id, the skill,
    the streak length) so the UI can explain *why* it was awarded.
    """

    __tablename__ = "user_achievements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Key from the achievement registry in app.services.achievements.
    achievement_key: Mapped[str] = mapped_column(String(80))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="achievements")

    __table_args__ = (
        # An achievement unlocks once per user, no matter how often we evaluate.
        Index("uq_user_achievement", "user_id", "achievement_key", unique=True),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<UserAchievement {self.achievement_key} user={self.user_id}>"
