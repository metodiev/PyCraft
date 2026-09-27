"""Submission records for both Run and Submit operations."""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.challenge import Challenge
    from app.models.user import User


class SubmissionKind(enum.StrEnum):
    """Run experiments against visible tests; Submit grades against the full suite."""

    RUN = "run"
    SUBMIT = "submit"


class SubmissionStatus(enum.StrEnum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"  # infrastructure/runner failure
    REJECTED = "rejected"  # refused by policy (bad payload, limits exceeded)


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    challenge_id: Mapped[str] = mapped_column(
        ForeignKey("challenges.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[SubmissionKind] = mapped_column(
        Enum(SubmissionKind, native_enum=False, length=10), default=SubmissionKind.RUN
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus, native_enum=False, length=20), default=SubmissionStatus.QUEUED
    )
    # {"solution.py": "<source>"} — a mapping keeps multi-file challenges possible.
    files: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    score: Mapped[int | None] = mapped_column(Integer, default=None)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    memory_used_mb: Mapped[float | None] = mapped_column(default=None)

    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)
    # Structured per-test results: [{name, status, duration_ms, message, hidden}].
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    user: Mapped[User] = relationship(back_populates="submissions")
    challenge: Mapped[Challenge] = relationship(back_populates="submissions")

    @property
    def is_graded(self) -> bool:
        return self.kind is SubmissionKind.SUBMIT and self.status is SubmissionStatus.COMPLETED
