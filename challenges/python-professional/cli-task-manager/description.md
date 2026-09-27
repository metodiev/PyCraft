# Project: CLI Task Manager

**This is a project, not a drill.** Three modules must cooperate — a model, a
store and a command layer — and the tests drive each one directly.

The point is not "write a to-do app". It is to show that you can keep
responsibilities apart: the model owns validity, the store owns identity and
persistence, and the CLI owns parsing and presentation.

| File | Responsibility |
| ---- | -------------- |
| `tasks.py` | What a task *is*: validation, normalisation, derived state |
| `storage.py` | Identity and durability: id assignment, filtering, atomic saves |
| `cli.py` | Parsing `argv` and formatting output — no file access |

## Your task

Implement the three modules so that the tests pass.

### `tasks.py`

| Name | Contract |
| ---- | -------- |
| `PRIORITIES` | `("low", "normal", "high", "urgent")`, ordered least to most urgent |
| `normalise_title(title)` | Collapse all runs of whitespace to single spaces; reject empty or longer than 120 characters |
| `normalise_priority(priority)` | Case-insensitive; reject anything outside `PRIORITIES` |
| `normalise_tags(tags)` | Lower-case, reject blanks and embedded whitespace, de-duplicate, return a **sorted tuple** |
| `Task` | Dataclass that normalises its fields on construction |
| `Task.to_dict()` / `Task.from_dict(raw)` | Round-trip through JSON-compatible primitives |
| `Task.is_overdue(today)` | True only when the due date is strictly before `today` and the task is not `done`/`archived` |
| `Task.can_transition_to(status)` | `archived` is terminal; every other status change is allowed |

### `storage.py`

`TaskStore(path, now=...)` loads the file if it exists and keeps tasks in memory.
It must:

- assign **monotonically increasing** ids that are never reused, even after
  deleting the highest id and reopening the file;
- persist through a temp file plus an atomic replace, so a crash cannot leave a
  half-written store, and no stray temp file survives a successful save;
- return tasks in a stable order: most urgent first, then earliest due date
  (tasks with no due date last), then lowest id;
- raise `TaskNotFoundError` for an unknown id and `TaskValidationError` for a
  store file that is not valid JSON;
- expose `add`, `get`, `all`, `update` and `delete`. `all` accepts optional
  `status`, `priority`, `tag` and `overdue_on` filters, combined with **and**.

`update(id, **changes)` only touches the fields you pass — `update(1, due=None)`
clears the due date. It rejects unknown field names.

### `cli.py`

`main(argv, store, out, today=None) -> int` parses `argv`, writes human-readable
lines to `out` and returns an exit code. It never opens a file itself.

```
add <title...> [--priority P] [--tag T]... [--due YYYY-MM-DD]
list [--status S] [--priority P] [--tag T] [--overdue]
show <id>
done <id>
rm <id>
```

| Exit code | Meaning |
| --------- | ------- |
| `EXIT_OK` (0) | Success |
| `EXIT_USAGE` (1) | Unknown command or malformed invocation |
| `EXIT_NOT_FOUND` (2) | The id does not exist |
| `EXIT_INVALID` (3) | The arguments are valid syntax but the values are rejected |

## Examples

```pycon
>>> store = TaskStore("tasks.json")
>>> main(["add", "write", "docs", "--priority", "high", "--tag", "api"], store, out)
0
>>> out.getvalue()
'added #1 [high] write docs (todo) #api\n'

>>> main(["done", "1"], store, out)
0
```

## Constraints

- Standard library only.
- `cli.py` must not import `json` or touch the filesystem.
- `tasks.py` must not import `storage.py` or `cli.py`.
- Sorting must respect **priority rank**, not the alphabetical order of the
  priority names.

## Hints

<details>
<summary>Hint 1 — Why a ranked priority exists</summary>

Sorting `["low", "normal", "high", "urgent"]` as strings gives
`["high", "low", "normal", "urgent"]` — wrong. Map each name to its index in
`PRIORITIES` and sort on that.

</details>

<details>
<summary>Hint 2 — Never reuse an id</summary>

Track the next id in the file alongside the tasks. On load, take
`max(stored_next_id, highest_existing_id + 1)` so a store written by an older
version, or one whose highest task was deleted, still moves forward.

</details>

<details>
<summary>Hint 3 — Atomic saves</summary>

Write to `path.with_name(path.name + ".tmp")`, then
`os.replace(tmp, path)`. `os.replace` is atomic on the same filesystem, so a
reader either sees the old file or the new one, never a partial write.

</details>

<details>
<summary>Hint 4 — Only change what was passed</summary>

Collect the changes into a dict and rebuild the task from it, rather than
rebuilding from defaults. That is what makes `due=None` mean "clear the date"
instead of "leave it alone".

</details>
