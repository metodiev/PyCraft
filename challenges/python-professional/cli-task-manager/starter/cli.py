"""Command-line front end.

This module owns *parsing and presentation*. It must not import ``json`` or
touch the filesystem: everything durable goes through the ``TaskStore`` it is
handed, which is what makes it testable without a real terminal.

Tests import ``main`` and the ``EXIT_*`` constants from here.
"""

from __future__ import annotations

from datetime import date
from typing import TextIO

from storage import TaskNotFoundError, TaskStore
from tasks import Task, TaskValidationError

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_NOT_FOUND = 2
EXIT_INVALID = 3

USAGE = (
    "usage: pycraft-tasks <command> [options]\n"
    "  add <title...> [--priority P] [--tag T]... [--due YYYY-MM-DD]\n"
    "  list [--status S] [--priority P] [--tag T] [--overdue]\n"
    "  show <id>\n"
    "  done <id>\n"
    "  rm <id>\n"
)


def format_task(task: Task) -> str:
    """Render one task as a single line.

    The shape is ``#<id> [<priority>] <title> (<status>)`` followed by
    ``due=<date>`` and ``#tag`` segments when present.
    """
    # TODO: implement. Keep it one line, and keep the segments in the order
    # documented above.
    raise NotImplementedError


def main(
    argv: list[str],
    store: TaskStore,
    out: TextIO,
    *,
    today: date | None = None,
) -> int:
    """Dispatch a command and return an exit code.

    ``today`` is injected so ``list --overdue`` is deterministic under test;
    fall back to ``date.today()`` when it is omitted.
    """
    # TODO: dispatch to add/list/show/done/rm, and map TaskNotFoundError to
    # EXIT_NOT_FOUND and TaskValidationError to EXIT_INVALID. An unknown
    # command is EXIT_USAGE.
    raise NotImplementedError
