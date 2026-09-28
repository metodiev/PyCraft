"""Per-user tutorial read state.

Tutorials are read, not solved, so this table is deliberately thin: it records
*that* a learner opened a tutorial, not a score. It carries no XP and never
feeds level calculation — the platform's rule is that completion is earned by
passing tests. The marker exists so a learner can see what they have covered and
find where they left off.

``tutorial_id`` is a plain string rather than a foreign key because tutorials
are authored as files and indexed in memory, not in a database table; a foreign
key would have nothing to point at. The catalogue is small enough that a stale
id (a tutorial deleted from disk) is filtered out when the view is built.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TutorialRead(Base, TimestampMixin):
    """One row per (user, tutorial) once the learner has opened it."""

    __tablename__ = "tutorial_reads"
    __table_args__ = (UniqueConstraint("user_id", "tutorial_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tutorial_id: Mapped[str] = mapped_column(String(120), index=True)
    # Set when the learner reaches the end of the article. Reading is self
    # reported: there is nothing to grade, and pretending otherwise would be
    # false precision.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    user: Mapped[User] = relationship(back_populates="tutorial_reads")
