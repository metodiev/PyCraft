"""User roles.

Kept in its own module so both ``user`` and the API dependencies can import it
without creating a cycle.
"""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    """Capability level.

    ``LEARNER`` can solve challenges. ``AUTHOR`` can also create and edit
    challenges. ``ADMIN`` can additionally manage users and publish content.
    """

    LEARNER = "learner"
    AUTHOR = "author"
    ADMIN = "admin"

    @property
    def rank(self) -> int:
        return {"learner": 0, "author": 1, "admin": 2}[self.value]

    def at_least(self, other: UserRole) -> bool:
        return self.rank >= other.rank
