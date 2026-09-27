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

## End to end

```bash
cd frontend
npx playwright install chromium   # once
npm run test:e2e
npm run test:e2e:ui               # watch mode
```

Playwright starts **both** servers itself — the API on port 8123 with the local
execution backend and its own SQLite file, the web dev server on 5273 — so there
is nothing to start first and the suite never touches `backend/.pycraft.db`.
Both ports are deliberately off the development defaults so an already-running
`npm run dev` cannot be mistaken for the suite's own servers.

**An existing server is not adopted by default.** Reuse looks harmless but
changes what is under test: a server left over from an earlier run answers on the
port with the configuration, database and bundle *it* was started with, and the
suite then reports real-looking failures in code that was never loaded. Set
`E2E_REUSE_SERVER=1` to opt in when iterating against servers you started on
purpose.

The API is launched with `.venv/bin/uvicorn`, which is correct locally. CI
installs the backend into the runner's interpreter, where that path does not
exist, so it overrides the launcher with `E2E_UVICORN="python -m uvicorn"`.

| Spec | Covers |
| --- | --- |
| `auth.spec.ts` | Register, sign in, sign out, wrong password, deep-link resume, password policy |
| `workspace.spec.ts` | Briefing and starter, Run output, grading a wrong and a right solution, draft persistence |
| `progress.spec.ts` | Catalogue listing, dashboard progress moving on success and not on failure |
| `authoring.spec.ts` | The role gate: an admin reaches the studio, a learner is refused it |

### Driving Monaco

Monaco keeps a hidden **read-only** textarea and intercepts key handling, so
synthetic input is unreliable: a `ControlOrMeta+A` press is dropped and the
typing that follows *appends* to the starter instead of replacing it. That
failure is worse than an untidy editor — the submission would be graded on code
the learner never wrote, and a test can pass its first assertion while doing it.

`fillEditor` therefore sets the editor **model** directly, reading the value back
to confirm it. The loader exposes the API on `window.monaco` for this, under
`import.meta.env.DEV || MODE === "test"` only; it is stripped from a production
bundle. This is why the helper takes fully indented source — nothing auto-indents
what is assigned to a model.

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

`.github/workflows/ci.yml` runs five jobs:

| Job | Checks |
| --- | --- |
| `backend` | Ruff lint + full fast test suite |
| `runner` | Builds the sandbox image, runs the `docker`-marked security tests |
| `frontend` | `tsc -b` + production build |
| `e2e` | Playwright against a real API and a real browser |
| `challenges` | Loads the catalogue with `strict=True` |

## What is not covered yet

- **No load testing.** `execution_concurrency` is a reasoned default, not a
  measured limit.
