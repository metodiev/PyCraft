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

Run and Submit are **asynchronous**. The request that starts one returns as soon
as the work is durable; the sandbox runs afterwards, and the caller polls.

1. **Frontend** posts `{files: {"solution.py": "..."}}` to
   `/api/v1/challenges/{id}/submit`.
2. **Pydantic** validates the payload — filename shape, per-file and total size
   limits, `.py` extension, no path separators ([`app/schemas/__init__.py`](../backend/app/schemas/__init__.py)).
3. **`SubmissionService.enqueue`** loads the challenge from the in-memory
   repository and persists a `Submission` row with status `queued`. Nothing
   executes yet, so the request is **not** held open by a container run.
4. **The response** is `202 Accepted` with a `submission_id` and a
   `submission_url`. The client polls `GET /api/v1/submissions/{id}` until
   `done` is true.
5. **A worker claims** the row — an atomic conditional `UPDATE` that takes the
   oldest runnable submission and stamps a lease. Two workers cannot claim one
   row, and a worker that dies mid-run loses its lease so the work is retried
   ([`app/services/queue.py`](../backend/app/services/queue.py)).
6. **Limits are clamped** to the platform ceiling. A challenge may lower the
   time/memory budget but never raise it.
7. **`DockerExecutionBackend`** acquires a concurrency semaphore, writes the
   payload JSON into a dedicated volume via a short-lived helper container, then
   starts a hardened sandbox container that mounts that volume read-only.
8. **Inside the container**, `entrypoint.py` materialises the files into a
   scratch directory, runs pytest as a subprocess with the challenge's own
   timeout, and prints a JSON report between marker lines.
9. **Backend parses** the report (ignoring anything the learner printed),
   normalises failures, and marks which tests were hidden.
10. **Scoring** produces a weighted score; hidden tests count for more than
    visible ones so iterating on visible tests alone cannot fake mastery.
11. **Progress** is updated — completion, XP, skill mastery — but only for
    submissions that actually pass, and only once per challenge. Because this
    happens in the worker, a submission that never runs cannot advance anyone's
    progress.
12. **A later poll** rebuilds the result from the stored row, so asking again
    long after the worker is gone returns the same answer. For Submit, raw
    process stdout is deliberately withheld so the hidden suite cannot be read
    back.

### Why a durable queue rather than Redis

Submissions are rows, not messages: a learner's work has to survive a restart,
a crash or a deploy, and the database is already the source of truth for
progress. An in-memory or Redis-only queue would add a second thing to keep
consistent and a new piece of infrastructure to run, for no gain at this scale —
the claim, the lease and the retry budget are all a few dozen lines of SQL.
Redis becomes worthwhile when workers move to separate machines and need a
wake-up signal; the enqueue path would not change.

The API process runs the workers by default, so a single container keeps working
(`PYCRAFT_RUN_WORKERS_IN_PROCESS=false` disables that when workers are deployed
separately). `GET /api/v1/queue` reports depth, worker count and how many
submissions have been processed, which is the smoke test that the pool is
draining rather than merely running.

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

A **project** is the same shape with several starter files. The loader infers
`kind: "project"` from a multi-file starter, so authors need not declare it. The
submission pipeline is shared: project files are merged over the starter before
execution, which means an unmodified helper still resolves at import time.

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

## Gamification and the skill graph

Achievements are **definitions in code** plus **unlock rows in the database**
([`app/services/achievements.py`](../backend/app/services/achievements.py)).
Adding one needs no migration, and re-evaluation is cheap: every predicate reads
a `LearnerSnapshot` built with a bounded number of queries, so evaluation never
becomes an N+1 problem as the catalogue grows.

Streaks count days on which a learner *solves* something, and lapse at read time
so a stale streak is never displayed. A two-day grace window tolerates a
late-night session crossing midnight.

The skill graph ([`app/services/skill_graph.py`](../backend/app/services/skill_graph.py))
is derived from content rather than maintained by hand: challenge metadata
declares which skills a challenge demonstrates, the roadmap declares each
stage's skill and prerequisites, and the graph joins both with the learner's
record. Adding a challenge therefore cannot leave the graph stale.

`app/services/roadmap.py` validates itself at import time — every `requires`
must name a real stage and skill ids must be unique — because a stale id once
silently produced a wrong graph rather than an error.

## AI assistance

Every provider is a scaffold, never a solution generator, and that is enforced
structurally rather than only by prompt
([`app/services/ai.py`](../backend/app/services/ai.py)):

- The sanitiser strips fenced code blocks and flags whole-solution phrasing,
  because a model can always ignore an instruction.
- Hint prompts are built from the challenge author's own hints, so generated
  guidance elaborates on curated material instead of inventing a shortcut.
- A fully filtered response becomes an error rather than an empty panel.
- The catalogue exposes no "write my code" capability at all.

Providers implement a two-method protocol, so swapping in a different vendor or
a self-hosted model touches one class. AI is disabled by default; every endpoint
returns a clear 503 explaining what to configure.

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
| A new sign-in provider | `AuthProvider` + a sibling to `services/github_oauth.py` |
| An achievement | One entry in the registry in `services/achievements.py` |
| Python 3.13 support | `runner/Dockerfile` + `SUPPORTED_PYTHON_VERSIONS` |

## Deliberate non-goals (for now)

- **Microservices.** The spec calls for service boundaries but explicitly warns
  against premature distribution. The backend is a modular monolith: `api/`,
  `services/`, `execution/`, `models/` are the seams along which services would
  later be extracted.
- **A job queue.** Execution is synchronous within the request. The concurrency
  semaphore bounds load; a Celery/Redis queue is the natural next step when
  submissions outgrow a single process.
- **Migrations.** The schema is created from the models at startup. Startup
  detects a development database missing columns and logs the remedy, but
  evolving a database with real data in it needs Alembic; see
  [database.md](./database.md#migrations).
- **Distributed rate limiting.** The AI rate limiter is an in-process sliding
  window. It is exact for a single worker and needs Redis for several, which is
  the same upgrade the job queue needs.
