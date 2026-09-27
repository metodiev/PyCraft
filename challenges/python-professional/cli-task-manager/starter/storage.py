"""Durable task storage backed by a JSON file.

The store owns *identity* and *durability*: assigning ids, filtering, ordering
and saving. It performs no formatting — that is the CLI's job.

Tests import ``TaskStore`` and ``TaskNotFoundError`` from here.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tasks import PRIORITIES, Task, TaskValidationError, normalise_priority

#: Written into the file so a future format change can be detected.
STORE_VERSION = 1


class TaskNotFoundError(LookupError):
    """Raised when a task id does not exist."""


class TaskStore:
    """A JSON-file-backed collection of tasks."""

    def __init__(self, path: str | Path, *, now: Callable[[], datetime] | None = None) -> None:
        self.path = Path(path)
        self._now = now or datetime.now
        self._tasks: dict[int, Task] = {}
        self._next_id = 1
        self.load()

    # --- persistence -----------------------------------------------------
    def load(self) -> None:
        """Read the store file into memory.

        A missing file means an empty store. A file that is not valid JSON, or
        not shaped like a store, must raise ``TaskValidationError``.
        """
        # TODO: read, validate and rehydrate. Derive the next id from both the
        # stored counter and the highest id present, so ids never go backwards.
        raise NotImplementedError

    def save(self) -> None:
        """Write the store atomically.

        Write a sibling ``.tmp`` file and ``os.replace`` it over the real one,
        so a reader never observes a partial write and no temp file survives.
        """
        # TODO: serialise deterministically (``sort_keys=True``) and replace
        # atomically.
        raise NotImplementedError

    # --- identity --------------------------------------------------------
    def add(
        self,
        title: str,
        *,
        priority: str = "normal",
        tags: Iterable[str] = (),
        due: date | None = None,
    ) -> Task:
        """Create and persist a task with the next free id."""
        # TODO: a rejected task must not consume an id.
        raise NotImplementedError

    def get(self, task_id: int) -> Task:
        """Return one task, or raise ``TaskNotFoundError``."""
        # TODO: implement.
        raise NotImplementedError

    def update(self, task_id: int, **changes: Any) -> Task:
        """Apply ``changes`` to a task and persist the result.

        Only the keys passed are touched, so ``update(1, due=None)`` clears the
        due date. Unknown keys and illegal status moves are rejected.
        """
        # TODO: validate, rebuild and save. Return the updated task.
        raise NotImplementedError

    def delete(self, task_id: int) -> None:
        """Remove a task, or raise ``TaskNotFoundError``."""
        # TODO: implement. Deleting the highest id must not free that id for
        # reuse.
        raise NotImplementedError

    # --- queries ---------------------------------------------------------
    def all(
        self,
        *,
        status: str | None = None,
        priority: str | None = None,
        tag: str | None = None,
        overdue_on: date | None = None,
    ) -> list[Task]:
        """Return the matching tasks in presentation order.

        Order: most urgent first, then earliest due date (undated tasks last),
        then lowest id. Every filter is optional and they combine with ``and``.
        """
        # TODO: implement filtering and ordering.
        raise NotImplementedError
