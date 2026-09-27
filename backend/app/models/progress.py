"""Per-user progress: challenge completion state and demonstrated skills."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class ProgressStatus(enum.StrEnum):
    AVAILABLE = "available"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ChallengeProgress(Base, TimestampMixin):
    """One row per (user, challenge) once the user has touched the challenge."""

    __tablename__ = "challenge_progress"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    challenge_id: Mapped[str] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ProgressStatus] = mapped_column(
        Enum(ProgressStatus, native_enum=False, length=20), default=ProgressStatus.AVAILABLE
    )
    best_score: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="challenge_progress")


class SkillProgress(Base, TimestampMixin):
    """Accumulated strength in a skill node of the skill graph."""

    __tablename__ = "skill_progress"
    __table_args__ = (UniqueConstraint("user_id", "skill"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    skill: Mapped[str] = mapped_column(String(120), index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    # 0-100, derived from the weighted score of the best attempt per challenge.
    mastery: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="skill_progress")
