# Testing

## Backend

```bash
cd backend
.venv/bin/pytest              # everything
.venv/bin/pytest -q           # no Docker needed, ~1s
.venv/bin/pytest -m docker    # real sandbox, ~25s
```

### Two tiers, deliberately

**Fast tier (default).** Runs against an in-process fake execution backend, a
temporary SQLite database, and a temporary challenge directory. It covers
challenge loading, report parsing, scoring and every API route — including the
full register → submit → progress journey — without Docker.

| File | Covers |
| --- | --- |
| `test_challenges.py` | Format validation, visible/hidden split, malformed content |
| `test_parser.py` | Runner output parsing, marker handling, malformed documents |
| `test_scoring.py` | Weighting, hidden-vs-visible credit, performance taper, quality |
| `test_api.py` | Every endpoint plus the end-to-end journey and validation |

**Docker tier (`-m docker`).** `test_docker_execution.py` spawns real containers.
This is the suite that proves the platform's security claims — network isolation,
read-only rootfs, unprivileged execution, resource caps, payload traversal
rejection, and cleanup. Run it before any change to `runner/` or the Docker
backend.

```bash
docker build -t pycraft-runner:3.12 -f runner/Dockerfile runner/
.venv/bin/pytest -m docker -v
```

### Isolation between tests

Each test gets its own SQLite file and challenge directory (via `tmp_path`), so
there is no shared state and no cleanup to forget. The fake backend records every
payload it receives, which is how tests assert that **Run never receives hidden
tests** — a security property, not an implementation detail.

## Frontend

```bash
cd frontend
npx tsc -b        # strict typecheck
npm run build     # production build
```

TypeScript runs with `strict`, `noUncheckedIndexedAccess`,
`exactOptionalPropertyTypes` and `noImplicitReturns`, so the API client's
response types are checked against real usage at compile time.

## Challenge content

Content is validated in CI by loading the whole catalogue with `strict=True`, so
a malformed challenge fails the build:

```bash
cd backend && PYTHONPATH=. .venv/bin/python -c "
from pathlib import Path
from app.services.challenges import ChallengeRepository
r = ChallengeRepository(Path('../challenges'))
print([c.id for c in r.load_all(strict=True)])
"
```

### Verifying a challenge actually discriminates

Format validation only proves a challenge is *well-formed*. To prove it is
*good*, check that it fails before and passes after:

1. Run the untouched starter against both suites — it must fail.
2. Write a correct solution — both suites must pass.
3. Write the **obvious naive** solution — it should pass the visible suite and
   fail at least one hidden test. If it passes everything, the hidden suite is
   not adding coverage.

See [challenge-format.md](./challenge-format.md) for the naive-implementation
table that maps common shortcuts to the hidden test that should catch them.

## CI

`.github/workflows/ci.yml` runs four jobs:

| Job | Checks |
| --- | --- |
| `backend` | Ruff lint + full fast test suite |
| `runner` | Builds the sandbox image, runs the `docker`-marked security tests |
| `frontend` | `tsc -b` + production build |
| `challenges` | Loads the catalogue with `strict=True` |

## What is not covered yet

- **No frontend test suite.** The UI is currently verified by typechecking and
  manual browser checks. Playwright is the intended next addition; the spec lists
  it in the stack.
- **No load testing.** `execution_concurrency` is a reasoned default, not a
  measured limit.
- **No migration tests.** There are no migrations yet; see
  [database.md](./database.md).
