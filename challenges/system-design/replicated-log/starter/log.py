"""The replicated log.

An append-only sequence of entries plus a commit index. Committed entries are
immutable: everything else in this project exists to protect them.

This module must not import ``node`` or ``cluster``.

Tests import ``Entry``, ``LogError`` and ``ReplicatedLog`` from here.
"""

from __future__ import annotations

from dataclasses import dataclass


class LogError(RuntimeError):
    """Raised when the log would be put into an illegal state."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One replicated write. ``index`` is 1-based; ``term`` is the leader's term."""

    term: int
    index: int
    value: str


class ReplicatedLog:
    """An ordered log with a commit index."""

    def __init__(self) -> None:
        self._entries: list[Entry] = []
        self._commit_index = 0

    # --- reading ---------------------------------------------------------
    @property
    def entries(self) -> list[Entry]:
        """Every entry, committed or not."""
        # TODO: return a copy, not the internal list.
        raise NotImplementedError

    @property
    def committed(self) -> list[Entry]:
        """Only the entries at or below the commit index."""
        # TODO: implement.
        raise NotImplementedError

    @property
    def commit_index(self) -> int:
        # TODO: implement.
        raise NotImplementedError

    @property
    def last_index(self) -> int:
        """Highest index present, or 0 when empty."""
        # TODO: implement.
        raise NotImplementedError

    @property
    def last_term(self) -> int:
        """Term of the last entry, or 0 when empty."""
        # TODO: implement.
        raise NotImplementedError

    def get(self, index: int) -> Entry:
        """Return one entry, or raise ``IndexError``."""
        # TODO: implement.
        raise NotImplementedError

    def term_at(self, index: int) -> int:
        """Term at ``index``; 0 for index 0 or an absent entry."""
        # TODO: implement.
        raise NotImplementedError

    def is_up_to_date(self, term: int, index: int) -> bool:
        """Whether ``(term, index)`` is at least as current as this log.

        Term is compared **first**. Comparing only the index lets a stale
        candidate win an election and overwrite committed history.
        """
        # TODO: implement.
        raise NotImplementedError

    # --- writing ---------------------------------------------------------
    def append(self, entry: Entry) -> None:
        """Append an entry.

        The index must be exactly ``last_index + 1`` and the term must not go
        backwards. Both violations raise ``LogError``.
        """
        # TODO: implement.
        raise NotImplementedError

    def truncate_from(self, index: int) -> None:
        """Drop every entry from ``index`` onward.

        Raises ``LogError`` if that would remove a committed entry — a
        committed entry can never be rewritten.
        """
        # TODO: implement.
        raise NotImplementedError

    def commit(self, index: int) -> None:
        """Advance the commit index.

        Monotonic: committing a lower index is a no-op, and committing beyond
        the end of the log raises ``LogError``.
        """
        # TODO: implement.
        raise NotImplementedError
