# Local development

## Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | 3.12 | The runtime the platform executes |
| Node.js | 22+ | Frontend toolchain |
| Docker | 24+ | Required for the execution sandbox |

Confirm Docker is reachable before starting — the API serves the catalogue
without it, but Run and Submit will fail:

```bash
docker info
```

On macOS with Colima: `colima start --cpu 2 --memory 4`.

## 1. Build the execution sandbox image

```bash
docker build -t pycraft-runner:3.12 -f runner/Dockerfile runner/
```

This must exist before the API starts, or submissions return
`503 Execution sandbox is unavailable`.

## 2. Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000>
- OpenAPI docs: <http://127.0.0.1:8000/docs>
- Default storage is SQLite at `backend/.pycraft.db` — no database to install.

Point it at PostgreSQL instead (the compose stack publishes it on 5433):

```bash
export PYCRAFT_DATABASE_URL="postgresql+asyncpg://pycraft:pycraft@localhost:5433/pycraft"
```

## 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

- App: <http://127.0.0.1:5173>
- `/api` is proxied to the backend, so no CORS setup is needed day to day.
- Override the proxy target with `VITE_API_TARGET` if the API runs elsewhere.

Sign-in lives entirely in the frontend; see
[frontend/README.md](../frontend/README.md#authentication) for how tokens are
stored, attached and refreshed.

## 4. Or: everything at once

```bash
./scripts/start.sh
```

Brings up PostgreSQL, Redis, the API, and the frontend (served by nginx on
<http://localhost:5173>), and verifies the result end to end — registering a
user and grading a real submission in the sandbox. Use it instead of
`docker compose up --build` unless you want the raw output: it checks the
environment first, explains failures, and logs everything to `scripts/logs/`.

```bash
./scripts/status.sh          # what is running, and is it healthy
./scripts/logs.sh api        # follow a service's log
./scripts/verify.sh          # prove grading works, without restarting
./scripts/stop.sh            # stop it (keeps your data)
./scripts/start.sh --help    # all the options
```

> **Development only.** The compose file mounts the Docker socket into the API
> container — that grants effective root on the host. See
> [security-model.md](./security-model.md#sandbox-trust-boundary).

PostgreSQL is published on **5433**, not 5432, so it does not collide with a
PostgreSQL already running on your machine. Inside the compose network the API
still reaches it as `postgres:5432`; only the host-side port differs.

If you run compose yourself, note that **list settings take a comma-separated
list or a JSON array** — `PYCRAFT_CORS_ORIGINS=http://a,http://b` and
`PYCRAFT_CORS_ORIGINS='["http://a","http://b"]'` are both accepted.

## Tests

```bash
cd backend

.venv/bin/pytest                 # unit + API tests, no Docker needed (~1s)
.venv/bin/pytest -m docker       # real sandbox: isolation and limits (~25s)
.venv/bin/pytest                 # everything
```

The `docker`-marked suite is the one that actually proves the security claims in
[security-model.md](./security-model.md) — it asserts that network access,
root writes, and privilege escalation are all blocked. Run it before any change
to `runner/` or the Docker backend.

Frontend:

```bash
cd frontend
npx tsc -b          # typecheck (strict)
npm run build       # production build
npx playwright install chromium   # once
npm run test:e2e    # end to end; starts both servers itself
```

The end-to-end suite needs no running servers and no prepared database — it
starts the API and the web server on their own ports and gives the API its own
SQLite file. See [testing.md](./testing.md#end-to-end).

## Linting

```bash
cd backend
.venv/bin/ruff check app tests          # lint
.venv/bin/ruff format app tests         # format
```

Optional pre-commit hooks (repository root):

```bash
pipx install pre-commit && pre-commit install
```

## Useful configuration

Every setting is an environment variable with a `PYCRAFT_` prefix, or a `.env`
file. The ones you are most likely to need:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PYCRAFT_DATABASE_URL` | SQLite file | Database connection string |
| `PYCRAFT_EXECUTION_BACKEND` | `docker` | `docker` or `local` (dev only) |
| `PYCRAFT_RUNNER_IMAGE` | `pycraft-runner:3.12` | Sandbox image to launch |
| `PYCRAFT_CHALLENGES_DIR` | `./challenges` | Challenge content root |
| `PYCRAFT_EXECUTION_CONCURRENCY` | `4` | Max simultaneous sandboxes |
| `PYCRAFT_MAX_TIME_LIMIT_MS` | `10000` | Hard ceiling a challenge cannot exceed |
| `PYCRAFT_MAX_MEMORY_LIMIT_MB` | `100` | Hard ceiling a challenge cannot exceed |
| `PYCRAFT_CORS_ORIGINS` | localhost:5173 | Comma-separated allowed origins |
| `PYCRAFT_ENVIRONMENT` | `development` | `development` \| `test` \| `production` |

### Running without Docker

Set `PYCRAFT_EXECUTION_BACKEND=local` to execute on the host.

> ⚠️ **This provides no isolation whatsoever** and is refused in production. It
> exists so contributors can iterate on the API, scoring, and frontend when
> Docker is unavailable. Never use it on a shared or internet-facing machine.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `503 Execution sandbox is unavailable` | Docker daemon not running, or the runner image is missing — build it (step 1) |
| `Runner image 'pycraft-runner:3.12' not found` in logs | Same as above; the message includes the exact build command |
| Challenge missing from the catalogue | Content is indexed at startup — restart the API and check the log for a `Challenge content problem` line |
| Submission hangs | The in-container timeout should fire first; check `docker ps` for a stuck container |
| `Cannot reach the PyCraft API` in the UI | Backend not running, or `VITE_API_TARGET` points at the wrong host |
| Port 5173 already in use | Another dev server is bound; stop it or set a different `server.port` in `vite.config.ts` |

## Cleaning up

```bash
# Sandbox containers and staging volumes should never outlive a request, but:
docker ps -a --filter label=pycraft=execution
docker volume ls --filter label=pycraft=payload-staging
```
