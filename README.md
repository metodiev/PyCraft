# PyCraft

PyCraft is an interactive Python engineering platform that takes developers from
**Junior Python Developer** to **Senior, Staff, Principal Engineer and Software
Architect** through progressively harder practical challenges.

It is not a tutorial site. The core loop is:

```
Learn → Code → Execute → Test → Debug → Improve → Progress
```

You write real Python in the browser, it runs in an isolated sandbox, and it is
graded against visible **and hidden** test suites. Completion is earned by
passing tests, never by marking a lesson read.

## How it works

```
React + Monaco        FastAPI                  Docker sandbox
  editor      ──▶   API + scoring   ──▶   python:3.12 + pytest
                    (runs no user code)     no network · read-only · unprivileged
```

The API server never executes user code — it only dispatches hardened containers
to the Docker daemon. See [docs/security-model.md](docs/security-model.md).

## Quick start

```bash
# 1. Build the execution sandbox
docker build -t pycraft-runner:3.12 -f runner/Dockerfile runner/

# 2. Backend (SQLite by default — no database to install)
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload

# 3. Frontend
cd ../frontend
npm install && npm run dev
```

Open <http://127.0.0.1:5173>. API docs at <http://127.0.0.1:8000/docs>.

Or bring the whole stack up with `docker compose up --build`.

Full instructions: [docs/development.md](docs/development.md).

## What's here

| Area | Status |
| --- | --- |
| Challenge catalogue with visible/hidden test split | ✅ |
| Monaco editor workspace with Run and Submit | ✅ |
| Docker-isolated Python 3.12 execution | ✅ |
| Resource limits: time, memory, CPU, PIDs, output | ✅ |
| Multi-dimensional scoring | ✅ |
| Dashboard: level, skills, roadmap, recent submissions | ✅ |
| 13-stage engineering roadmap | ✅ |
| Authentication: email/password, GitHub OAuth, sessions, reset | ✅ |
| Profile management and active-session control | ✅ |
| Roles: learner / author / admin | ✅ |
| Gamification: 20 achievements, streaks, leaderboards | ✅ |
| Skill graph with prerequisite edges | ✅ |
| Challenge authoring API with validation and publishing | ✅ |
| Multi-file project challenges with rubrics | ✅ |
| AI assistance: hints, explanations, reviews (leak-guarded) | ✅ |
| CI: lint, tests, sandbox security tests, content validation | ✅ |
| Challenge authoring UI | ⏳ API only |
| More curriculum across all 13 tracks | ⏳ 10 of 13 tracks |
| The remaining real-world projects | ✅ 8 of 8 |

## Repository layout

```
backend/     FastAPI service — catalogue, scoring, progress, execution dispatch
  app/
    api/         HTTP routes
    execution/   Sandbox backends (Docker, local-dev) + report parsing
    models/      SQLAlchemy models
    services/    Challenge loading, scoring, roadmap, submission orchestration
    schemas/     Pydantic request/response contracts
challenges/  Challenge content, authored as files and indexed at startup
frontend/    React + TypeScript + Vite + Monaco
runner/      The Python 3.12 execution image and its entrypoint
docs/        Architecture, security, API, execution, database, testing, deployment
```

## Development

```bash
cd backend
.venv/bin/pytest              # fast suite, no Docker required
.venv/bin/pytest -m docker    # real sandbox: isolation and limit tests
.venv/bin/ruff check app tests
```

```bash
cd frontend
npx tsc -b      # strict typecheck
npm run build
```

## Documentation

| Document | Covers |
| --- | --- |
| [architecture.md](docs/architecture.md) | System design, request lifecycle, extension points |
| [security-model.md](docs/security-model.md) | Threat model, container hardening, residual risks |
| [api.md](docs/api.md) | Every endpoint with request/response examples |
| [execution.md](docs/execution.md) | The execution pipeline, payload contract, limits |
| [challenge-format.md](docs/challenge-format.md) | How to author a challenge, including hidden-test strategy |
| [database.md](docs/database.md) | Schema, migrations, progress semantics |
| [testing.md](docs/testing.md) | Test tiers and how to verify a challenge discriminates |
| [deployment.md](docs/deployment.md) | Production topology, configuration, operations |

## Adding a challenge

Challenges are directories — no code required:

```
challenges/<track>/<slug>/
├── metadata.json
├── description.md
├── starter/solution.py
└── tests/
    ├── test_visible.py
    └── test_hidden.py
```

See [docs/challenge-format.md](docs/challenge-format.md). CI validates the format
and rejects malformed content.

## License

See [LICENSE](LICENSE).
