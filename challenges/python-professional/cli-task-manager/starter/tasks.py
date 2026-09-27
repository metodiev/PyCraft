"""Task model, validation and derived state.

This module owns *what a task is*: which values are legal, how tags are
normalised, and which status changes are permitted. It performs no I/O and must
not import ``storage`` or ``cli``.

Tests import ``PRIORITIES``, ``Task``, ``TaskValidationError``,
``normalise_priority``, ``normalise_tags`` and ``normalise_title`` from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

# Ordered least urgent -> most urgent. Sorting by *position* is what the store
# needs; sorting these names as strings would put "high" before "low".
PRIORITIES: tuple[str, ...] = ("low", "normal", "high", "urgent")

STATUSES: tuple[str, ...] = ("todo", "doing", "done", "archived")

# A task in one of these states is finished and therefore never overdue.
CLOSED_STATUSES: frozenset[str] = frozenset({"done", "archived"})

# The only status a task cannot leave.
TERMINAL_STATUSES: frozenset[str] = frozenset({"archived"})

MAX_TITLE_LENGTH = 120
MAX_TAG_LENGTH = 24


class TaskValidationError(ValueError):
    """Raised when a task would be constructed or transitioned illegally."""


def normalise_title(title: str) -> str:
    """Return a clean title, or raise ``TaskValidationError``.

    Runs of whitespace (spaces, tabs, newlines) collapse to a single space, so
    two titles that differ only in spacing compare equal.
    """
    # TODO: collapse whitespace, then reject an empty or over-long result.
    raise NotImplementedError


def normalise_priority(priority: str) -> str:
    """Return the canonical lower-case priority name, or raise."""
    # TODO: accept any casing, reject names outside PRIORITIES.
    raise NotImplementedError


def normalise_tags(tags: Any) -> tuple[str, ...]:
    """Return tags lower-cased, de-duplicated and sorted.

    De-duplicating and sorting makes tag equality order-independent: passing
    ``["API", "api", "docs"]`` and ``["docs", "api"]`` must agree.
    """
    # TODO: a bare string is not a sequence of tags; blanks and embedded
    # whitespace are invalid; the result is a sorted tuple.
    raise NotImplementedError


@dataclass
class Task:
    """One unit of work."""

    id: int
    title: str
    priority: str = "normal"
    status: str = "todo"
    tags: tuple[str, ...] = ()
    due: date | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        # TODO: normalise title/priority/tags in place and reject an illegal
        # id, status, due or created_at. Note that ``datetime`` is a subclass
        # of ``date``, so check for it first if you reject it.
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-compatible primitives."""
        # TODO: dates and datetimes become ISO 8601 strings.
        raise NotImplementedError

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Task:
        """Rehydrate a task produced by :meth:`to_dict`."""
        # TODO: parse the ISO strings back, and report bad input as
        # TaskValidationError rather than leaking KeyError/TypeError.
        raise NotImplementedError

    def is_overdue(self, today: date) -> bool:
        """Whether the task is overdue as of ``today``."""
        # TODO: no due date, or a closed status, means never overdue. The due
        # date equal to ``today`` is not yet late.
        raise NotImplementedError

    def can_transition_to(self, status: str) -> bool:
        """Whether this task may move to ``status``."""
        # TODO: a terminal task only "transitions" to its current status.
        raise NotImplementedError
