"""Indexed challenge metadata.

The authoritative copy of a challenge lives on disk
(``challenges/<slug>/``); this table is a query-friendly projection used for
listing, roadmap rendering and progress joins.
"""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Challenge(Base, TimestampMixin):
    __tablename__ = "challenges"

    # Human-authored slug, e.g. "python-functions-001".
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(400), default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner")
    track: Mapped[str] = mapped_column(String(60), index=True)
    module: Mapped[str] = mapped_column(String(60), index=True)
    python_version: Mapped[str] = mapped_column(String(20), default="3.12")
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=5_000)
    memory_limit_mb: Mapped[int] = mapped_column(Integer, default=128)
    points: Mapped[int] = mapped_column(Integer, default=100)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    # Skills demonstrated by solving this challenge, e.g. ["python.functions"].
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Relative path of the entry file inside the challenge directory.
    entry_file: Mapped[str] = mapped_column(String(120), default="starter/solution.py")
    # Generated summary of assertion counts used for progress display.
    tests_summary: Mapped[str] = mapped_column(Text, default="")
    # "challenge" for a focused exercise, "project" for a multi-file build.
    kind: Mapped[str] = mapped_column(String(20), default="challenge")

    submissions: Mapped[list[Submission]] = relationship(  # noqa: F821
        back_populates="challenge", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Challenge {self.id} ({self.difficulty})>"
