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

### Overview

PyCraft issues two tokens:

| Token | Format | Lifetime | Revocable |
| --- | --- | --- | --- |
| Access token | Signed JWT | 15 min | Indirectly (via its session) |
| Refresh token | Opaque random string | 30 days | Yes |

Send the access token as `Authorization: Bearer <token>`. On `401`, exchange the
refresh token for a new pair.

**Refresh tokens rotate.** Each `/auth/refresh` consumes the presented token and
issues a new one. Replaying a consumed token is treated as theft: **every**
session for that user is revoked immediately. Store the newest refresh token and
never retry a request with an old one.

Logout and password change take effect immediately, because the access token
names a session that is checked against the database on every request.

### Endpoints

#### `GET /auth/config`

Public — lets the UI hide disabled options.

```json
{
  "password_auth_enabled": true,
  "registration_enabled": true,
  "github_enabled": false,
  "min_password_length": 10
}
```

#### `POST /auth/register`

```json
{ "email": "ada@example.com", "password": "Correct-Horse-9", "display_name": "Ada" }
```

Returns `201` with a `TokenResponse`. Emails are normalised to lowercase.

Password policy: at least 10 characters, at least one letter, at least one digit.
Unknown fields are rejected (`422`).

Errors: `409` if the email is already registered · `403` if registration is
disabled · `422` on a weak password or invalid email.

#### `POST /auth/login`

```json
{ "email": "ada@example.com", "password": "Correct-Horse-9" }
```

Returns `TokenResponse`. A wrong password and an unknown email produce an
**identical** `401`, so the endpoint cannot be used to enumerate accounts.

#### `POST /auth/refresh`

```json
{ "refresh_token": "<token>" }
```

Returns a fresh `TokenResponse`. `401` if the token is unknown, expired, revoked,
or has already been used.

#### `POST /auth/logout`

```json
{ "refresh_token": "<token>" }
```

Revokes that session. Always returns `200`, even for an unknown token
(idempotent).

#### `GET /auth/me`

Returns the caller's `UserProfile`. Requires authentication.

```json
{
  "id": "…",
  "email": "ada@example.com",
  "display_name": "Ada Lovelace",
  "role": "learner",
  "avatar_url": "",
  "headline": "Backend engineer",
  "bio": "…",
  "location": "London",
  "website": "https://example.com",
  "xp": 250,
  "current_streak": 4,
  "longest_streak": 11,
  "last_active_date": "2026-09-27",
  "is_admin": false,
  "has_password": true,
  "linked_providers": [],
  "created_at": "2026-09-01T10:00:00Z"
}
```

#### `PATCH /auth/me`

Partial update of `display_name`, `headline`, `bio`, `location`, `website`.
Omitted fields are left unchanged; `role` and `xp` are rejected (`422`) so they
cannot be self-assigned.

#### `POST /auth/me/password`

```json
{ "current_password": "Correct-Horse-9", "password": "Even-Better-Pass-7" }
```

Revokes **all** sessions, including the caller's, so the client must sign in
again. `400` if the current password is wrong.

#### `GET /auth/me/sessions` · `DELETE /auth/me/sessions/{id}`

List active sessions (the current one is flagged `is_current`) and revoke one by
id. Session ids are scoped to the caller; another user's id returns `404`.

#### `POST /auth/password/reset-request`

```json
{ "email": "ada@example.com" }
```

Always returns the same `200` message, whether or not the address is registered.
With the `console` email backend the reset link is written to the server log
instead of being sent.

#### `POST /auth/password/reset-confirm`

```json
{ "token": "<from the email link>", "password": "Even-Better-Pass-7" }
```

Single-use; the token is invalidated on success and revokes all sessions. `400`
on an invalid or expired token.

### GitHub OAuth

Browser-navigated endpoints, not JSON API calls.

| Endpoint | Purpose |
| --- | --- |
| `GET /auth/github/authorize?redirect_to=/` | Redirects to GitHub |
| `GET /auth/github/callback` | GitHub redirects here; signs the user in |
| `GET /auth/github/status` | Whether it is configured |

The callback ends by redirecting to
`<frontend_base_url><redirect_to>#access_token=…&refresh_token=…`. Tokens travel
in the **fragment** so they are never sent to a server, and the frontend strips
them from the URL immediately.

`redirect_to` is carried inside a signed, 10-minute, single-purpose JWT. A
hostile value (`https://evil.example.com`, `//evil.example.com`) is discarded in
favour of `/`, and an access token cannot be used in place of a state value.

Account linking: an existing account with the same **verified** email is reused
rather than duplicated. Unverified GitHub emails are refused, since accepting one
could hand over another user's account.

### Roles

| Role | Can |
| --- | --- |
| `learner` | Solve challenges |
| `author` | Also create and edit challenges |
| `admin` | Also manage users and publish content |

Grant admin via `PYCRAFT_ADMIN_EMAILS` (applied at registration):

```bash
PYCRAFT_ADMIN_EMAILS=you@example.com,teammate@example.com
```

Admin endpoints: `GET /auth/users`, `PATCH /auth/users/{id}/role?role=<role>`.
An admin cannot demote their own account, which prevents locking the last
administrator out.

### Public vs protected endpoints

| Endpoint group | Auth |
| --- | --- |
| `/auth/config`, `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/password/*`, `/auth/github/*` | Public |
| `/challenges` (browse), `/runtime`, `/health` | Public |
| `/challenges/{id}/run`, `/challenges/{id}/submit` | Required |
| `/dashboard`, `/progress`, `/roadmap`, `/skills` | Required |
| `/auth/me*`, `/auth/users*` | Required (admin for the last) |

Browsing the catalogue signed out works and shows no personal progress.

## Error format

FastAPI's standard shapes apply:

```json
{ "detail": "Challenge 'nope' does not exist" }
```

```json
{ "detail": [ { "loc": ["body", "files"], "msg": "…", "type": "…" } ] }
```

Authentication failures additionally carry `WWW-Authenticate: Bearer`.

| Status | Meaning |
| --- | --- |
| `401` | Missing, malformed, or expired credentials; session ended |
| `403` | Authenticated but not permitted (disabled account, insufficient role) |
| `404` | Resource does not exist, or is not visible to the caller |
| `409` | Conflict (email already registered) |
| `422` | Request body failed validation |
| `503` | Execution sandbox unavailable |
