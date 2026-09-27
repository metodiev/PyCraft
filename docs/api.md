# PyCraft API

Base path: `/api/v1`. Interactive docs (OpenAPI) are served at `/docs`.

All responses are JSON. Every request currently resolves to a single demo
identity; see [Authentication](#authentication).

## Runtime

### `GET /health`

Liveness probe. Mounted outside the versioned prefix so it is stable.

```json
{ "status": "ok" }
```

### `GET /runtime`

Which sandbox and Python versions are in use — powers the header badge.

```json
{
  "execution_backend": "docker",
  "python_versions": ["3.12"],
  "default_python_version": "3.12",
  "environment": "development",
  "challenge_count": 5
}
```

## Challenges

### `GET /challenges`

Catalogue with the caller's completion state. Optional `?track=<track-id>`.

```json
[
  {
    "id": "python-fundamentals-hello-world",
    "title": "Hello, World",
    "summary": "Return your first formatted string from a Python function.",
    "difficulty": "beginner",
    "track": "python-fundamentals",
    "module": "Getting Started",
    "level": "junior",
    "python_version": "3.12",
    "points": 50,
    "order_index": 1,
    "skills": ["python.basics", "python.fundamentals"],
    "tags": ["strings", "functions", "basics"],
    "visible_test_count": 1,
    "skill_mastery": 0,
    "completed": false,
    "best_score": 0
  }
]
```

### `GET /challenges/{id}`

Adds the briefing, starter code and visible tests. **Hidden tests are never
included in any response.**

```json
{
  "id": "python-fundamentals-hello-world",
  "...": "(all fields from the list endpoint)",
  "description": "# Hello, World\n\n…",
  "starter_code": "def greet(name: str) -> str:\n    …",
  "entry_file": "solution.py",
  "time_limit_ms": 5000,
  "memory_limit_mb": 128,
  "visible_tests": { "test_visible.py": "from solution import greet\n…" }
}
```

`404` if the challenge does not exist.

## Run and Submit

Both accept the same body.

```json
{
  "files": {
    "solution.py": "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n"
  }
}
```

Validation (`422` on failure):

- 1–10 files, each ending in `.py`, bare filenames only
- no path separators (`/`, `\`) or `..`
- each file ≤ 128 KB, ≤ 256 KB total
- no empty files
- unknown top-level fields rejected

### `POST /challenges/{id}/run`

Experimental run against **visible tests only**. Returns raw output for
debugging; no score, no progress change.

```json
{
  "submission_id": "d2466afb-449b-43f5-9fa5-7464a06a834f",
  "status": "completed",
  "stdout": "... 3 passed in 0.01s\n",
  "stderr": "",
  "exit_code": 0,
  "execution_time_ms": 501,
  "memory_used_mb": 33.5
}
```

### `POST /challenges/{id}/submit`

Graded against the **complete suite** (visible + hidden).

```json
{
  "submission_id": "…",
  "status": "completed",
  "score": 100,
  "passed": 8,
  "failed": 0,
  "total_tests": 8,
  "execution_time_ms": 506,
  "memory_used_mb": 33.2,
  "results": [
    {
      "name": "test_visible.py::test_greets_world",
      "status": "passed",
      "duration_ms": 0,
      "message": "",
      "hidden": false
    },
    {
      "name": "test_hidden.py::test_empty_name",
      "status": "failed",
      "duration_ms": 0,
      "message": "",
      "hidden": true
    }
  ],
  "dimensions": [
    { "name": "correctness", "score": 100, "weight": 100, "detail": "8/8 tests passed" }
  ],
  "summary": "Excellent — all 8 tests passed.",
  "progress": { "...": "see GET /progress" }
}
```

Notes on the response:

- **Raw `stdout`/`stderr` are intentionally absent** so hidden tests cannot be
  read back (see [security-model.md](./security-model.md)).
- `message` is always empty for hidden tests.
- `status` is `completed`, `timeout`, `failed` or `rejected`. A timeout scores 0
  and is reported as `completed` in the submission record because the run itself
  finished normally.

`404` unknown challenge · `503` execution sandbox unavailable.

## Progress

### `GET /progress`

```json
{
  "xp": 50,
  "level_id": "junior",
  "level_label": "Junior",
  "xp_into_level": 50,
  "next_level_label": "Intermediate",
  "next_level_xp": 1000,
  "completed_challenges": 1,
  "total_challenges": 5,
  "completion_pct": 20
}
```

### `GET /dashboard`

Everything the dashboard needs in one round trip: `progress`, `skills`,
`roadmap`, `recent_submissions`, `recommended_challenge`, `continue_challenge`.

### `GET /roadmap`

All 13 progression stages, each annotated with `total_challenges`,
`completed_challenges` and `progress_pct`. Stages without content yet are
returned with zeroes rather than omitted, so the UI can show them as upcoming.

### `GET /skills`

Per-skill mastery.

```json
[
  {
    "skill": "python.basics",
    "label": "Python Basics",
    "mastery": 100,
    "xp": 10,
    "challenges_completed": 1,
    "challenges_total": 2
  }
]
```

## Authentication

Every endpoint resolves the acting user through a single FastAPI dependency,
`current_user`. Today that returns a shared demo account, or the identity named
by the `X-PyCraft-User` header:

```bash
curl -H "X-PyCraft-User: learner@example.com" http://localhost:8000/api/v1/progress
```

This header is a **development convenience, not authentication** — it is
self-asserted and must be replaced by real sessions before any multi-user
deployment. Because all routes depend on `current_user`, that replacement is
contained to one function.

## Error format

FastAPI's standard shapes apply:

```json
{ "detail": "Challenge 'nope' does not exist" }
```

```json
{ "detail": [ { "loc": ["body", "files"], "msg": "…", "type": "…" } ] }
```
