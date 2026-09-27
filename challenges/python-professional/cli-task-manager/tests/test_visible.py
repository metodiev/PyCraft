"""Visible tests — the basic contract for each module."""

import io
from datetime import date, datetime

import pytest

from cli import EXIT_INVALID, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from storage import TaskNotFoundError, TaskStore
from tasks import (
    Task,
    TaskValidationError,
    normalise_priority,
    normalise_tags,
    normalise_title,
)

FIXED_NOW = datetime(2026, 1, 1, 9, 0)


@pytest.fixture()
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.json", now=lambda: FIXED_NOW)


# --- model ---------------------------------------------------------------
def test_title_whitespace_is_collapsed():
    assert normalise_title("  write   the   docs ") == "write the docs"


def test_blank_title_is_rejected():
    with pytest.raises(TaskValidationError):
        normalise_title("   ")


def test_priority_is_case_insensitive():
    assert normalise_priority("HIGH") == "high"


def test_unknown_priority_is_rejected():
    with pytest.raises(TaskValidationError):
        normalise_priority("whenever")


def test_tags_are_lowercased_and_deduplicated():
    assert normalise_tags(["API", "api", "Docs"]) == ("api", "docs")


def test_a_bare_string_is_not_a_tag_sequence():
    with pytest.raises(TaskValidationError):
        normalise_tags("api")


def test_task_round_trips_through_a_dict():
    task = Task(
        id=1,
        title="Ship it",
        priority="high",
        tags=("api",),
        due=date(2026, 2, 1),
        created_at=FIXED_NOW,
    )

    assert Task.from_dict(task.to_dict()) == task


def test_task_is_overdue_only_after_the_due_date():
    task = Task(id=1, title="Ship it", due=date(2026, 1, 1))

    assert task.is_overdue(date(2026, 1, 2)) is True
    assert task.is_overdue(date(2026, 1, 1)) is False


# --- storage -------------------------------------------------------------
def test_add_assigns_increasing_ids(store):
    assert store.add("first").id == 1
    assert store.add("second").id == 2


def test_get_returns_the_task(store):
    created = store.add("first")

    assert store.get(created.id) == created


def test_get_unknown_id_raises(store):
    with pytest.raises(TaskNotFoundError):
        store.get(99)


def test_tasks_survive_reopening_the_file(tmp_path):
    store = TaskStore(tmp_path / "tasks.json", now=lambda: FIXED_NOW)
    store.add("persisted", priority="high", tags=["api"])

    reopened = TaskStore(tmp_path / "tasks.json", now=lambda: FIXED_NOW)
    tasks = reopened.all()

    assert [task.title for task in tasks] == ["persisted"]
    assert tasks[0].priority == "high"
    assert tasks[0].tags == ("api",)


def test_filtering_by_status(store):
    store.add("open one")
    finished = store.add("finished one")
    store.update(finished.id, status="done")

    assert [task.title for task in store.all(status="todo")] == ["open one"]
    assert [task.title for task in store.all(status="done")] == ["finished one"]


def test_delete_removes_the_task(store):
    task = store.add("gone")
    store.delete(task.id)

    with pytest.raises(TaskNotFoundError):
        store.get(task.id)


# --- cli -----------------------------------------------------------------
def test_cli_add_reports_the_new_task(store):
    out = io.StringIO()

    assert main(["add", "write", "docs"], store, out) == EXIT_OK
    assert "#1" in out.getvalue()
    assert "write docs" in out.getvalue()


def test_cli_list_shows_the_added_task(store):
    main(["add", "write docs"], store, io.StringIO())
    out = io.StringIO()

    assert main(["list"], store, out) == EXIT_OK
    assert "#1" in out.getvalue()


def test_cli_unknown_command_is_a_usage_error(store):
    assert main(["explode"], store, io.StringIO()) == EXIT_USAGE


def test_cli_unknown_id_is_not_found(store):
    assert main(["show", "42"], store, io.StringIO()) == EXIT_NOT_FOUND


def test_cli_invalid_priority_is_rejected(store):
    assert main(["add", "x", "--priority", "whenever"], store, io.StringIO()) == EXIT_INVALID
