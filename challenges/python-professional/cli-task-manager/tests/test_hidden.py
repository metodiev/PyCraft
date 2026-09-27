"""Hidden tests — the details that separate a working store from a correct one."""

import io
import json
import os
from datetime import date, datetime

import pytest

from cli import EXIT_INVALID, EXIT_NOT_FOUND, EXIT_OK, EXIT_USAGE, main
from storage import TaskNotFoundError, TaskStore
from tasks import (
    PRIORITIES,
    Task,
    TaskValidationError,
    normalise_tags,
    normalise_title,
)

FIXED_NOW = datetime(2026, 1, 1, 9, 0)


@pytest.fixture()
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.json", now=lambda: FIXED_NOW)


def titles(tasks):
    return [task.title for task in tasks]


# --- ordering: the classic "sort the names" bug --------------------------
def test_ordering_respects_priority_rank_not_the_alphabet(store):
    """Sorting the priority names as strings puts high before low."""
    for name in reversed(PRIORITIES):
        store.add(f"task {name}", priority=name)

    assert titles(store.all()) == [
        "task urgent",
        "task high",
        "task normal",
        "task low",
    ]


def test_due_date_breaks_ties_within_a_priority(store):
    store.add("later", priority="high", due=date(2026, 3, 1))
    store.add("earlier", priority="high", due=date(2026, 2, 1))

    assert titles(store.all()) == ["earlier", "later"]


def test_undated_tasks_sort_last_within_a_priority(store):
    store.add("undated", priority="high")
    store.add("dated", priority="high", due=date(2026, 12, 1))

    assert titles(store.all()) == ["dated", "undated"]


def test_lowest_id_breaks_remaining_ties(store):
    first = store.add("same", priority="high", due=date(2026, 2, 1))
    second = store.add("same", priority="high", due=date(2026, 2, 1))

    assert [task.id for task in store.all()] == [first.id, second.id]


# --- identity ------------------------------------------------------------
def test_deleting_the_highest_id_does_not_free_it(tmp_path):
    """Reusing an id silently corrupts any reference a caller is holding."""
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    store.add("first")
    third = store.add("third")

    store.delete(third.id)

    assert store.add("fourth").id > third.id


def test_ids_keep_climbing_after_a_reopen(tmp_path):
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    store.add("first")
    store.add("second")
    store.delete(2)
    store.save()

    reopened = TaskStore(path, now=lambda: FIXED_NOW)

    assert reopened.add("third").id == 3


def test_a_rejected_add_does_not_consume_an_id(store):
    """Ids are a scarce resource; a validation failure must not burn one."""
    with pytest.raises(TaskValidationError):
        store.add("   ")

    assert store.add("first").id == 1


def test_ids_are_recovered_when_the_counter_is_stale(tmp_path):
    """A store written without a counter must still not hand out a used id."""
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"tasks": [{"id": 7, "title": "seventh"}]}), encoding="utf-8")

    store = TaskStore(path, now=lambda: FIXED_NOW)

    assert store.add("next").id == 8


# --- durability ----------------------------------------------------------
def test_a_successful_save_leaves_no_temp_file(tmp_path):
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    store.add("first")

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "tasks.json"]

    assert leftovers == [], f"stray files after save: {leftovers}"


def test_the_original_file_survives_a_failed_read(tmp_path):
    """A corrupt store must be reported, not silently truncated."""
    path = tmp_path / "tasks.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(TaskValidationError):
        TaskStore(path, now=lambda: FIXED_NOW)

    assert path.read_text(encoding="utf-8") == "{not json"


def test_a_failed_swap_keeps_the_previous_contents(tmp_path, monkeypatch):
    """Persistence is all-or-nothing: never a half-written file."""
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    store.add("first")
    before = path.read_text(encoding="utf-8")

    def failing_replace(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)

    with pytest.raises(OSError):
        store.save()

    assert path.read_text(encoding="utf-8") == before


def test_the_store_is_valid_json_after_saving(tmp_path):
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    store.add("first", tags=["b", "a"], due=date(2026, 2, 1))

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert isinstance(payload, dict)
    assert any(task["title"] == "first" for task in payload["tasks"])


# --- partial updates -----------------------------------------------------
def test_update_touches_only_the_keys_passed(store):
    """Rebuilding from defaults would silently reset everything else."""
    task = store.add("original", priority="urgent", tags=["api"], due=date(2026, 5, 1))

    store.update(task.id, status="done")
    updated = store.get(task.id)

    assert updated.title == "original"
    assert updated.priority == "urgent"
    assert updated.tags == ("api",)
    assert updated.due == date(2026, 5, 1)
    assert updated.status == "done"


def test_update_can_clear_the_due_date(store):
    task = store.add("dated", due=date(2026, 5, 1))

    store.update(task.id, due=None)

    assert store.get(task.id).due is None


def test_update_rejects_unknown_fields(store):
    task = store.add("original")

    with pytest.raises(TaskValidationError):
        store.update(task.id, nonexistent="x")


def test_update_rejects_an_illegal_transition(store):
    task = store.add("archived later")
    store.update(task.id, status="archived")

    with pytest.raises(TaskValidationError):
        store.update(task.id, status="todo")


def test_update_rejects_an_unknown_priority(store):
    task = store.add("original")

    with pytest.raises(TaskValidationError):
        store.update(task.id, priority="whenever")


def test_update_of_an_unknown_id_raises(store):
    with pytest.raises(TaskNotFoundError):
        store.update(99, status="done")


def test_updates_are_persisted(tmp_path):
    path = tmp_path / "tasks.json"
    store = TaskStore(path, now=lambda: FIXED_NOW)
    task = store.add("original")
    store.update(task.id, title="renamed")

    assert TaskStore(path, now=lambda: FIXED_NOW).get(task.id).title == "renamed"


# --- filtering -----------------------------------------------------------
def test_filters_combine_with_and(store):
    store.add("both", priority="high", tags=["api"])
    store.add("tag only", tags=["api"])
    store.add("priority only", priority="high")

    assert titles(store.all(priority="high", tag="api")) == ["both"]


def test_tag_filter_matches_the_normalised_tag(store):
    store.add("tagged", tags=["API"])

    assert titles(store.all(tag="api")) == ["tagged"]


def test_overdue_filter_excludes_closed_and_undated_tasks(store):
    store.add("late and open", due=date(2026, 1, 5))
    late_done = store.add("late but done", due=date(2026, 1, 5))
    store.add("no date")
    store.update(late_done.id, status="done")

    overdue = store.all(overdue_on=date(2026, 2, 1))

    assert titles(overdue) == ["late and open"]


def test_filters_do_not_mutate_the_store(store):
    store.add("first", priority="high")
    store.add("second", priority="low")

    store.all(priority="high")
    after = store.all()

    assert len(after) == 2


# --- model details -------------------------------------------------------
def test_tags_are_sorted_and_unique_while_case_folding():
    assert normalise_tags(["Zebra", "apple", "APPLE"]) == ("apple", "zebra")


def test_tags_may_not_contain_whitespace():
    with pytest.raises(TaskValidationError):
        normalise_tags(["two words"])


def test_an_over_long_title_is_rejected():
    with pytest.raises(TaskValidationError):
        normalise_title("x" * 200)


def test_titles_of_exactly_the_limit_are_accepted():
    assert len(normalise_title("x" * 120)) == 120


def test_duplicate_tags_collapse_on_a_task():
    task = Task(id=1, title="t", tags=("api", "API", "docs"))

    assert task.tags == ("api", "docs")


def test_from_dict_reports_missing_fields_as_validation_errors():
    with pytest.raises(TaskValidationError):
        Task.from_dict({"id": 1})


def test_from_dict_reports_a_bad_date_as_a_validation_error():
    with pytest.raises(TaskValidationError):
        Task.from_dict({"id": 1, "title": "t", "due": "not-a-date"})


def test_a_negative_id_is_rejected():
    with pytest.raises(TaskValidationError):
        Task(id=-1, title="t")


def test_an_unknown_status_is_rejected():
    with pytest.raises(TaskValidationError):
        Task(id=1, title="t", status="sleeping")


def test_archived_is_terminal():
    archived = Task(id=1, title="t", status="archived")

    assert archived.can_transition_to("archived") is True
    assert archived.can_transition_to("todo") is False


def test_an_open_task_may_move_anywhere():
    open_task = Task(id=1, title="t", status="todo")

    assert all(open_task.can_transition_to(status) for status in ("todo", "doing", "done", "archived"))


def test_done_tasks_are_never_overdue():
    done = Task(id=1, title="t", status="done", due=date(2020, 1, 1))

    assert done.is_overdue(date(2026, 1, 1)) is False


def test_archived_tasks_are_never_overdue():
    archived = Task(id=1, title="t", status="archived", due=date(2020, 1, 1))

    assert archived.is_overdue(date(2026, 1, 1)) is False


def test_a_task_without_a_due_date_is_never_overdue():
    undated = Task(id=1, title="t")

    assert undated.is_overdue(date(2026, 1, 1)) is False


def test_to_dict_produces_json_serialisable_values():
    task = Task(id=1, title="t", due=date(2026, 2, 1), created_at=FIXED_NOW)

    assert json.loads(json.dumps(task.to_dict()))["due"] == "2026-02-01"


# --- cli -----------------------------------------------------------------
def test_cli_done_marks_the_task_complete(store):
    store.add("finish me")
    out = io.StringIO()

    assert main(["done", "1"], store, out) == EXIT_OK
    assert store.get(1).status == "done"


def test_cli_rm_deletes_the_task(store):
    store.add("remove me")

    assert main(["rm", "1"], store, io.StringIO()) == EXIT_OK
    assert store.all() == []


def test_cli_show_includes_the_title(store):
    store.add("visible task")
    out = io.StringIO()

    assert main(["show", "1"], store, out) == EXIT_OK
    assert "visible task" in out.getvalue()


def test_cli_add_joins_a_multi_word_title(store):
    out = io.StringIO()

    assert main(["add", "write", "the", "docs"], store, out) == EXIT_OK
    assert store.get(1).title == "write the docs"


def test_cli_add_accepts_repeated_tags(store):
    main(["add", "tagged", "--tag", "api", "--tag", "docs"], store, io.StringIO())

    assert store.get(1).tags == ("api", "docs")


def test_cli_add_rejects_a_malformed_due_date(store):
    assert main(["add", "x", "--due", "tomorrow"], store, io.StringIO()) == EXIT_INVALID


def test_cli_add_stores_the_priority(store):
    main(["add", "x", "--priority", "URGENT"], store, io.StringIO())

    assert store.get(1).priority == "urgent"


def test_cli_invalid_arguments_are_a_usage_error(store):
    assert main(["add"], store, io.StringIO()) == EXIT_USAGE
    assert main(["add", "x", "--priority"], store, io.StringIO()) == EXIT_USAGE


def test_cli_a_non_numeric_id_is_a_usage_error(store):
    assert main(["show", "abc"], store, io.StringIO()) == EXIT_USAGE


def test_cli_list_filters_by_tag(store):
    main(["add", "keep", "--tag", "api"], store, io.StringIO())
    main(["add", "drop", "--tag", "docs"], store, io.StringIO())
    out = io.StringIO()

    assert main(["list", "--tag", "api"], store, out) == EXIT_OK
    assert "keep" in out.getvalue()
    assert "drop" not in out.getvalue()


def test_cli_list_overdue_uses_the_injected_today(store):
    store.add("late", due=date(2026, 1, 5))
    store.add("not yet", due=date(2026, 12, 1))
    out = io.StringIO()

    assert main(["list", "--overdue"], store, out, today=date(2026, 2, 1)) == EXIT_OK
    assert "late" in out.getvalue()
    assert "not yet" not in out.getvalue()


def test_cli_done_on_an_unknown_id_is_not_found(store):
    assert main(["done", "42"], store, io.StringIO()) == EXIT_NOT_FOUND


def test_cli_does_not_import_json():
    """Persistence belongs to the store; the CLI must stay storage-agnostic."""
    import cli

    assert not hasattr(cli, "json"), "cli.py must not import json"
