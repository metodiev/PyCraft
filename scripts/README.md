# Scripts

Start, stop and inspect the whole PyCraft platform in Docker.

```bash
./scripts/start.sh          # check, build, start, verify
./scripts/status.sh         # is it healthy?
./scripts/logs.sh           # what is it doing?
./scripts/stop.sh           # stop it
```

Nothing here is needed to *develop* PyCraft — the backend and frontend each run
on their own (see [development.md](../docs/development.md)). These scripts are
for running the real stack: PostgreSQL, Redis, the API and the web UI, wired
together the way they would be in production.

| Script | What it does |
| --- | --- |
| `start.sh` | Preflight checks, build, start, and verify end to end |
| `stop.sh` | Stop everything, optionally removing data and images |
| `status.sh` | One screen: containers, endpoints, queue, row counts |
| `logs.sh` | Read or follow service logs |
| `restart.sh` | Restart everything, or one service |
| `verify.sh` | Prove grading works against a running platform |
| `lib/common.sh` | Shared helpers (sourced, not run) |

## start.sh

```bash
./scripts/start.sh                  # the normal path
./scripts/start.sh --no-verify      # skip the end-to-end submission check
./scripts/start.sh --recreate       # rebuild images and recreate containers
./scripts/start.sh --foreground     # follow the logs instead of detaching
./scripts/start.sh --force-port     # move a port instead of refusing to start
PYCRAFT_VERBOSE=1 ./scripts/start.sh   # show every check, not just the results
```

It runs five phases and prints what it checked at each one:

1. **Preflight** — Docker CLI, compose, the daemon, free ports, disk space, the
   source tree, and the Docker socket.
2. **Build** — the sandbox image first (the platform cannot work without it),
   then the API and web images.
3. **Start** — `compose up`, then waits for each service to report *healthy*
   rather than merely running.
4. **Verify** — `/runtime` (proves startup finished and the catalogue loaded),
   the queue (proves the workers are alive), and the web proxy.
5. **End to end** — registers a user and grades a real submission in a real
   sandbox, so a broken grading path cannot pass unnoticed.

Everything is written to `scripts/logs/start.log`, including the full output of
every command it runs.

### Ports

| Service | Host port | Override |
| --- | --- | --- |
| PostgreSQL | 5433 | `PYCRAFT_POSTGRES_PORT` |
| Redis | 6379 | `PYCRAFT_REDIS_PORT` |
| API | 8000 | `PYCRAFT_API_PORT` |
| Web UI | 5173 | `PYCRAFT_WEB_PORT` |

PostgreSQL is on 5433 to avoid a collision with a PostgreSQL already running on
the machine. Only the *host* side changes — the API still reaches it as
`postgres:5432` inside the compose network.

A port held by another process makes `start.sh` stop and tell you who holds it.
It does not kill anything on its own. `--force-port` moves PyCraft's own ports
to free ones instead.

### The Docker socket

The API needs the Docker socket to spawn execution sandboxes, and two things
about it are easy to get wrong — both of which fail in ways that look like
application bugs:

- **The path is daemon-side.** On colima and Docker Desktop the daemon runs in a
  VM where the socket is always `/var/run/docker.sock`, even though no such file
  exists on the host. Mounting the host-side path fails with
  `error while creating mount source path`.
- **The API runs unprivileged.** The socket is mode `660` owned by the daemon's
  group, so the API must join that group. Without it every connection is
  refused, and submissions fail with *"Execution backend is not available"*
  while the container still reports healthy.

`start.sh` checks both — the second by opening a real connection as the API's
own user — and `status.sh` re-checks it. The group id differs per install (991
on colima, 0 on Docker Desktop), so it is detected at run time;
`PYCRAFT_DOCKER_GID` overrides it.

## Safety

- Every command targets containers labelled
  `com.docker.compose.project=pycraft`. Another project's containers are never
  touched, even if they use the same image.
- `stop.sh` keeps your data by default. `--volumes` deletes the database and
  asks first.
- Nothing is killed by process name. `--orphans` only stops a leftover process
  if its command line points inside this repository.

## Requirements

Docker and either `docker compose` or the standalone `docker-compose` (Homebrew
installs only the latter, which the Docker CLI does not discover on its own —
both are handled). `jq`, `curl` and `lsof` are used for checks; the scripts say
so plainly if one is missing.

Written for the bash 3.2 that ships with macOS, so no bash 4 features.
