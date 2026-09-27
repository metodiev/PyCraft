# Architecture

PyCraft is a training platform where learners write real Python, execute it in an
isolated sandbox, and are graded against visible and hidden test suites.

This document explains how the pieces fit together and why they are shaped that
way. For threat-model details see [security-model.md](./security-model.md).

## System overview

```
┌─────────────────────┐
│  React frontend     │  Vite + TypeScript + Monaco
│  (frontend/)        │
└──────────┬──────────┘
           │ REST (JSON)
           ▼
┌─────────────────────┐
│  FastAPI backend    │  Challenge catalogue, scoring, progress
│  (backend/)         │  ── never executes user code ──
└──────────┬──────────┘
           │ Docker API (spawn sandbox)
           ▼
┌─────────────────────┐
│  Runner container   │  python:3.12-slim, pytest, no network
│  (runner/)          │  read-only rootfs, unprivileged, resource-capped
└─────────────────────┘
```

Data lives in PostgreSQL (SQLite for local development). Challenges are authored
as files in `challenges/`, reviewed in pull requests, and indexed into the
database at API startup.

## Why the API never runs user code

The single most important design decision: **the API process only ever talks to
the Docker daemon.** It never imports, `eval`s, or subprocesses a learner's
source. That means a sandbox escape is required for an attacker to reach the API,
rather than merely a successful code submission.

The `ExecutionBackend` abstraction ([`app/execution/base.py`](../backend/app/execution/base.py))
is the seam. Two implementations exist:

| Backend | Used for | Isolation |
| --- | --- | --- |
| `DockerExecutionBackend` | Development and production | Container per submission, hardened flags |
| `LocalExecutionBackend` | Offline development only | **None** — refuses to start in production |

Because the contract is a protocol, an execution backend for Kubernetes, AWS
Lambda, or a dedicated runner fleet can be added without touching the API layer.

## Request lifecycle: submitting a solution

1. **Frontend** posts `{files: {"solution.py": "..."}}` to
   `/api/v1/challenges/{id}/submit`.
2. **Pydantic** validates the payload — filename shape, per-file and total size
   limits, `.py` extension, no path separators ([`app/schemas/__init__.py`](../backend/app/schemas/__init__.py)).
3. **`SubmissionService`** loads the challenge from the in-memory repository,
   builds an `ExecutionPayload`, and persists a `Submission` row with status
   `queued`.
4. **Limits are clamped** to the platform ceiling. A challenge may lower the
   time/memory budget but never raise it.
5. **`DockerExecutionBackend`** acquires a concurrency semaphore, writes the
   payload JSON into a dedicated volume via a short-lived helper container, then
   starts a hardened sandbox container that mounts that volume read-only.
6. **Inside the container**, `entrypoint.py` materialises the files into a
   scratch directory, runs pytest as a subprocess with the challenge's own
   timeout, and prints a JSON report between marker lines.
7. **Backend parses** the report (ignoring anything the learner printed),
   normalises failures, and marks which tests were hidden.
8. **Scoring** produces a weighted score; hidden tests count for more than
   visible ones so iterating on visible tests alone cannot fake mastery.
9. **Progress** is updated — completion, XP, skill mastery — but only for
   submissions that actually pass, and only once per challenge.
10. **The response** returns per-test results. For Submit, raw process stdout is
    deliberately withheld so the hidden suite cannot be read back.

## Why `put_archive` stages into a volume

The obvious implementation — copy the payload into the sandbox with
`docker cp` — **does not work** with `--read-only`: Docker writes through the
container's root filesystem layer, so the copy is rejected even when the target
is a tmpfs mount. Staging into a named volume from a separate helper container
sidesteps this, and has the side benefit of not requiring the API host to share
a filesystem with the Docker daemon (which matters for Docker Desktop, Colima,
and remote `DOCKER_HOST` setups).

## Challenge format

Challenges are directories, which makes them reviewable, diffable, and
greppable:

```
challenges/<track>/<slug>/
├── metadata.json         # id, difficulty, limits, skills, points
├── description.md        # learner-facing briefing (Markdown)
├── starter/solution.py   # code shown in the editor
└── tests/
    ├── test_visible.py   # shown to the learner
    └── test_hidden.py    # graded only
```

The loader ([`app/services/challenges.py`](../backend/app/services/challenges.py))
enforces invariants in CI: `id` must equal `<track>-<slug>`, the track must match
its directory, an entry file must exist, and there must be at least one visible
and one hidden test. A malformed challenge fails the build rather than silently
disappearing from the catalogue.

Test files split by filename: `test_hidden*.py` is graded-only, everything else
is visible. At run time the starter is normalised to `solution.py`, so authors
can name their entry file whatever they like while tests always
`from solution import ...`.

## Scoring

Correctness is the only dimension that can be measured objectively from a
sandbox run today, and it dominates beginner work. Advanced challenges also
weight performance (measured against the time limit) and a static quality
heuristic (does it parse, is it documented, are placeholder markers left).

The dimension weights are data, not control flow
([`app/services/scoring.py`](../backend/app/services/scoring.py)), so adding test
quality, security, or architecture signals later is a table change plus one
function, not a refactor. Weighted correctness is 60% hidden / 40% visible.

## Frontend structure

```
src/
├── api/client.ts        # Typed API client mirroring backend schemas
├── components/          # Reusable UI: cards, badges, Markdown, test results
├── hooks/useApi.ts      # Minimal fetch-state hook
├── lib/                 # Monaco setup, level definitions
├── pages/               # Dashboard, challenge list, workspace, roadmap
└── styles/tokens.css    # Design tokens (dark, IDE-adjacent palette)
```

The workspace deliberately claims the full viewport (see the `:has(.workspace)`
rule in `components/layout.css`) because an editor squeezed into a reading
column is not usable for real work.

Drafts are mirrored to `localStorage` on a debounce, so an accidental refresh
never destroys in-progress work.

## Extension points

| To add… | Touch |
| --- | --- |
| A new challenge | A new directory under `challenges/` — no code |
| A new language/track | `roadmap.py` stage + challenge metadata |
| A new execution substrate | A new `ExecutionBackend` implementation |
| A new scoring dimension | The `WEIGHTS` table + a scoring function |
| Authentication | `current_user` in [`app/api/deps.py`](../backend/app/api/deps.py) |
| Python 3.13 support | `runner/Dockerfile` + `SUPPORTED_PYTHON_VERSIONS` |

## Deliberate non-goals (for now)

- **Microservices.** The spec calls for service boundaries but explicitly warns
  against premature distribution. The backend is a modular monolith: `api/`,
  `services/`, `execution/`, `models/` are the seams along which services would
  later be extracted.
- **A job queue.** Execution is synchronous within the request. The concurrency
  semaphore bounds load; a Celery/Redis queue is the natural next step when
  submissions outgrow a single process.
- **Real authentication.** A single demo identity is resolved by
  `current_user`. Every route already depends on that seam, so adding sessions
  is additive.
