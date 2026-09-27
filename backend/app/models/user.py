"""User accounts and profiles."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.roles import UserRole

if TYPE_CHECKING:
    from app.models.auth import LinkedAccount, PasswordResetToken, Session
    from app.models.gamification import UserAchievement
    from app.models.progress import ChallengeProgress, SkillProgress
    from app.models.submission import Submission


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    # Argon2id hash; nullable because OAuth-only accounts have no password.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), default=UserRole.LEARNER
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    xp: Mapped[int] = mapped_column(default=0)

    # --- Profile ---------------------------------------------------------
    bio: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(120), default="")
    website: Mapped[str] = mapped_column(String(200), default="")
    avatar_url: Mapped[str] = mapped_column(String(500), default="")
    headline: Mapped[str] = mapped_column(String(160), default="")

    # --- Streaks ---------------------------------------------------------
    current_streak: Mapped[int] = mapped_column(default=0)
    longest_streak: Mapped[int] = mapped_column(default=0)
    # A date (not a timestamp) so "consecutive days" is timezone-independent.
    last_active_date: Mapped[date | None] = mapped_column(Date, default=None)

    submissions: Mapped[list[Submission]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    challenge_progress: Mapped[list[ChallengeProgress]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    skill_progress: Mapped[list[SkillProgress]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    linked_accounts: Mapped[list[LinkedAccount]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    password_resets: Mapped[list[PasswordResetToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achievements: Mapped[list[UserAchievement]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN

    @property
    def initials(self) -> str:
        parts = [part for part in self.display_name.split() if part]
        if not parts:
            return self.email[:1].upper()
        return "".join(part[0].upper() for part in parts[:2])

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email} ({self.role})>"
