"""Authentication persistence: sessions, refresh tokens, password resets."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.user import User


def is_past(value: datetime | None) -> bool:
    """Timezone-safe expiry check.

    SQLite discards tzinfo, so a value written as UTC can read back naive.
    Comparing naive to aware raises ``TypeError``, so treat anything without
    tzinfo as UTC — which is what every writer in this codebase stores.
    """
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= datetime.now(UTC)


class AuthProvider(enum.StrEnum):
    PASSWORD = "password"
    GITHUB = "github"


class Session(Base, TimestampMixin):
    """A signed-in device.

    Refresh tokens rotate: each use issues a new token and revokes the used one,
    so a stolen token is usable at most once and the theft is detectable (the
    original holder's next refresh fails).
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 of the current refresh token; the plaintext is never stored.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, native_enum=False, length=20), default=AuthProvider.PASSWORD
    )
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and not is_past(self.expires_at)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Session {self.id} user={self.user_id} active={self.is_active}>"


class PasswordResetToken(Base, TimestampMixin):
    """A single-use password reset link.

    ``used_at`` makes the token single-use. Lookups go through the hash, so the
    plaintext token exists only in the email that was sent.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    requested_ip: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User] = relationship(back_populates="password_resets")

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not is_past(self.expires_at)


# Composite index for the common "active sessions for this user" query.
Index("ix_sessions_user_active", Session.user_id, Session.revoked_at)


class LinkedAccount(Base, TimestampMixin):
    """An external identity (GitHub today) bound to a PyCraft user."""

    __tablename__ = "linked_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, native_enum=False, length=20)
    )
    # Provider-side immutable identifier (GitHub's numeric id as a string).
    provider_user_id: Mapped[str] = mapped_column(String(120))
    provider_login: Mapped[str] = mapped_column(String(120), default="")
    access_token: Mapped[str | None] = mapped_column(String(255), default=None)

    user: Mapped[User] = relationship(back_populates="linked_accounts")

    __table_args__ = (
        # One identity per provider, and one link per provider per user.
        Index("uq_linked_provider_identity", "provider", "provider_user_id", unique=True),
        Index("uq_linked_user_provider", "user_id", "provider", unique=True),
    )
