# Deployment

## Topology

```
        ┌──────────────┐
        │  Reverse     │  TLS termination, static assets
        │  proxy / CDN │
        └──────┬───────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
┌───────────┐    ┌──────────────┐
│ Frontend  │    │  API         │  no user code
│ (static)  │───▶│  (uvicorn)   │
└───────────┘    └──────┬───────┘
                        │  Docker API
                        ▼
                 ┌──────────────┐
                 │ Execution    │  sandboxes
                 │ daemon/node  │
                 └──────────────┘
```

Scale the API horizontally. Scale execution by adding daemon capacity, which is
the actual bottleneck — every in-flight submission costs a container.

## Configuration

All settings come from `PYCRAFT_`-prefixed environment variables; see
[development.md](./development.md#useful-configuration) for the full list.

Production baseline:

```bash
PYCRAFT_ENVIRONMENT=production
PYCRAFT_DEBUG=false

# Never SQLite in production.
PYCRAFT_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/pycraft
PYCRAFT_DB_POOL_SIZE=10

# Exact origins — no wildcards with credentials enabled.
PYCRAFT_CORS_ORIGINS=https://pycraft.example.com

# Execution ceilings.
PYCRAFT_EXECUTION_BACKEND=docker
PYCRAFT_RUNNER_IMAGE=pycraft-runner:3.12
PYCRAFT_EXECUTION_CONCURRENCY=8
PYCRAFT_MAX_TIME_LIMIT_MS=10000
PYCRAFT_MAX_MEMORY_LIMIT_MB=512

PYCRAFT_CHALLENGES_DIR=/app/challenges
```

## Deployment steps

1. **Build and push images**

   ```bash
   docker build -t registry/pycraft-runner:3.12 -f runner/Dockerfile runner/
   docker build -t registry/pycraft-api:$(git rev-parse --short HEAD) -f backend/Dockerfile backend/
   docker build -t registry/pycraft-web:$(git rev-parse --short HEAD) -f frontend/Dockerfile frontend/
   docker push registry/pycraft-runner:3.12
   docker push registry/pycraft-api:$(git rev-parse --short HEAD)
   docker push registry/pycraft-web:$(git rev-parse --short HEAD)
   ```

   The runner image must be present on every host that will execute sandboxes.

2. **Provision PostgreSQL** and apply migrations (see
   [database.md](./database.md#migrations)).

3. **Deploy the API** with a reachable Docker daemon. Do **not** mount
   `/var/run/docker.sock` from the production host — that grants effective root.
   Use dedicated execution nodes and point the API at them via
   `PYCRAFT_DOCKER_HOST`, or run the sandboxes through a rootless/VM-isolated
   runtime.

4. **Deploy the frontend** as static assets. Build with
   `VITE_API_TARGET` pointing at the API, or serve behind a proxy that routes
   `/api` (the bundled `nginx.conf` does exactly this).

5. **Verify**

   ```bash
   curl -fsS https://pycraft.example.com/health
   curl -fsS https://pycraft.example.com/api/v1/runtime
   ```

   `execution_backend` must be `docker`, never `local`.

## Reverse proxy

`frontend/nginx.conf` is a working reference: SPA fallback, immutable caching for
hashed assets, gzip, and `/api` proxying with a 60-second read timeout.

## Health checks

| Endpoint | Use |
| --- | --- |
| `/health` | Liveness. Unversioned so it is stable. |
| `/api/v1/runtime` | Readiness — confirms catalogue and backend state |

`/api/v1/runtime` returns `execution_backend: "unavailable"` when the sandbox
could not be reached. The API still serves the catalogue and dashboard in that
state, so treat it as *degraded* rather than *down*, and alert on it separately.

## Operational notes

### Backup

Back up PostgreSQL. Challenge content is in git. Nothing else is stateful — the
staging volumes and sandbox containers are ephemeral by design.

### Monitoring

Watch:

- Sandbox container startup latency (the dominant per-submission cost).
- The `execution_concurrency` semaphore's queue depth. Sustained saturation
  means adding execution capacity, not raising the limit.
- `timeout` and `rejected` rates. A spike in either is worth investigating —
  timeouts often mean a challenge's limit is too tight, rejections can indicate
  probing.

### Cleanup

Containers and volumes are removed in a `finally` block, so a crash mid-execution
can leak them. Sweep periodically:

```bash
docker ps -a --filter label=pycraft=execution --filter status=exited
docker volume ls --filter label=pycraft=payload-staging
```

### Costs

The execution sandbox dominates. Every submission is a container start on top of
the work itself, so cheap challenges still cost a container start. Keep the
runner image small (it is `python:3.12-slim` plus pytest) and consider a warm
pool once volume justifies it.
