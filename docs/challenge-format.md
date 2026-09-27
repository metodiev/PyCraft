# Challenge authoring

A challenge is a directory under `challenges/<track>/<slug>/`. Content is files,
not database rows, so it is reviewable in pull requests, diffable, and
greppable. The API indexes it at startup.

## Layout

```
challenges/<track>/<slug>/
├── metadata.json         # required
├── description.md        # required
├── starter/
│   └── solution.py       # required (name configurable via entry_file)
└── tests/
    ├── test_visible.py   # required (>=1)
    └── test_hidden.py    # required (>=1)
```

## `metadata.json`

```json
{
  "id": "python-fundamentals-hello-world",
  "title": "Hello, World",
  "summary": "Return your first formatted string from a Python function.",
  "difficulty": "beginner",
  "track": "python-fundamentals",
  "module": "Getting Started",
  "level": "junior",
  "python_version": "3.12",
  "time_limit_ms": 5000,
  "memory_limit_mb": 128,
  "points": 50,
  "order_index": 1,
  "skills": ["python.basics", "python.fundamentals"],
  "entry_file": "solution.py",
  "tags": ["strings", "functions", "basics"]
}
```

| Field | Required | Notes |
| --- | --- | --- |
| `id` | ✅ | Must equal `<track>-<slug>`, and `<slug>` must match the directory name |
| `title` | ✅ | Shown in lists and the editor header |
| `track` | ✅ | Must match the parent directory |
| `difficulty` | ✅ | `beginner` \| `easy` \| `intermediate` \| `advanced` \| `expert` — selects scoring weights |
| `summary` | | One sentence, truncated at 400 chars |
| `module` | | Grouping within a track (`"Collections"`) |
| `level` | | `junior` \| `intermediate` \| `senior` \| `staff` \| `principal` |
| `python_version` | | Defaults to `3.12` |
| `time_limit_ms` | | Defaults to 5000; **clamped** to the platform ceiling |
| `memory_limit_mb` | | Defaults to 128; **clamped** to the platform ceiling |
| `points` | | XP awarded on first pass |
| `order_index` | | Sort order within the track |
| `skills` | | Dotted skill ids — these drive the dashboard skill graph |
| `entry_file` | | Defaults to `solution.py` |
| `tags` | | Free-form discovery tags |

Validation is strict and runs in CI: a malformed challenge fails the build
rather than quietly vanishing from the catalogue.

## Tests

```python
# tests/test_visible.py — the learner sees this
from solution import greet


def test_greets_world():
    assert greet("World") == "Hello, World!"
```

```python
# tests/test_hidden.py — graded only, never shown
from solution import greet


def test_empty_name():
    assert greet("") == "Hello, !"
```

**The contract:** the entry file is materialised as `solution.py` next to the
tests, so every test starts with `from solution import …`. You can name your
entry file anything (`entry_file` in metadata); the platform normalises it.

Split rules:

- `test_hidden*.py` → hidden, graded on Submit, never sent to the browser
- everything else (`test_visible.py`, `test_edge_cases.py`, …) → visible

### Writing good hidden tests

Hidden tests are the platform's whole quality signal — if they are weak,
learners can pass by satisfying the visible suite alone. Aim for tests that a
plausible naive implementation fails:

| Naive implementation | Hidden test that catches it |
| --- | --- |
| Splits on whitespace only | Punctuation and mixed separators |
| Lowercases but ignores digits | Alphanumeric word boundaries |
| Uses `\w` (matches Unicode letters) | Non-ASCII letters must not count |
| Handles the happy path only | Empty input, single element, all-duplicates |
| Mutates its argument in place | The caller's list must be unchanged |

A good measure: write the obvious naive solution, confirm it passes
`test_visible.py`, and confirm it **fails** `test_hidden.py`.

### Test environment

- CPython 3.12 + pytest + pytest-asyncio. **Standard library only** — no
  third-party imports beyond pytest.
- No network access.
- Runs as an unprivileged user with a read-only root filesystem; only the
  scratch directory and `/tmp` are writable.
- A fixture failure is reported as an `error`, not a `failed`, and counts
  against the score.

## `description.md`

Rendered with a Markdown subset: headings, paragraphs, lists, tables, fenced
code, inline code, bold/italic, links, and `<details>` blocks for hints.

Structure that works well:

```markdown
# Title

One-paragraph framing.

## Your task

What to implement, stated unambiguously.

## Examples

| Input | Expected result |
| ----- | --------------- |
| `"World"` | `"Hello, World!"` |

## Constraints

- Standard library only
- Must not mutate the input

## Hints

<details>
<summary>Hint 1 — Getting started</summary>

Progressive hints, each hidden by default.
</details>
```

Write the task so it is solvable from the description alone. The starter file
should carry a docstring, a `# TODO:` marker, and a `NotImplementedError` body.

## Local workflow

```bash
# 1. Scaffold
mkdir -p challenges/<track>/<slug>/{starter,tests}

# 2. Write the files, then validate the format
cd backend && .venv/bin/python -c "
from pathlib import Path
from app.services.challenges import ChallengeRepository
r = ChallengeRepository(Path('../challenges'))
print([c.id for c in r.load_all(strict=True)], r.errors)
"

# 3. Verify the challenge actually discriminates: the starter must fail and a
#    correct solution must pass, for BOTH suites:
.venv/bin/pytest -m docker    # sandbox integration tests
```

Restart the API to pick up new content (the catalogue is indexed at startup).

## Checklist before opening a PR

- [ ] `id` equals `<track>-<slug>` and matches the directory
- [ ] At least one visible and one hidden test
- [ ] Starter raises `NotImplementedError`; the challenge is not pre-solved
- [ ] A correct solution passes visible **and** hidden tests in the sandbox
- [ ] A naive solution fails at least one hidden test
- [ ] `description.md` states the task, shows examples, and offers hints
- [ ] `skills` ids match the roadmap vocabulary in
      [`app/services/roadmap.py`](../backend/app/services/roadmap.py)
- [ ] No credentials or private data anywhere, especially in hidden tests
