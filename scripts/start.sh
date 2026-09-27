#!/usr/bin/env bash
#
# Start the whole PyCraft platform in Docker.
#
#   ./scripts/start.sh                 # checks, builds, starts, verifies
#   ./scripts/start.sh --no-verify     # skip the smoke test
#   ./scripts/start.sh --foreground    # follow logs instead of detaching
#   ./scripts/start.sh --recreate      # rebuild images and recreate containers
#   ./scripts/start.sh --force-port    # move a port instead of refusing to start
#
# What it does, in order:
#
#   1. Preflight — Docker, compose, daemon, source tree, ports, disk, socket
#   2. Reconcile — tear down a stale stack of ours, never anyone else's
#   3. Build    — runner image (the sandbox) then the API and web images
#   4. Start    — bring the stack up and wait for real readiness, not just ports
#   5. Verify   — register a user and grade a real submission end to end
#
# Every step logs what it checked and what it found. Use PYCRAFT_VERBOSE=1 for
# the full detail; the same detail is always written to scripts/logs/.

# --- Argument parsing --------------------------------------------------------
NO_VERIFY=0
FOREGROUND=0
RECREATE=0
FORCE_PORT=0
SKIP_BUILD=0
for arg in "$@"; do
  case "${arg}" in
    --no-verify)  NO_VERIFY=1 ;;
    --foreground | -f) FOREGROUND=1 ;;
    --recreate)   RECREATE=1 ;;
    --force-port) FORCE_PORT=1 ;;
    --no-build)   SKIP_BUILD=1 ;;
    --verbose | -v) PYCRAFT_VERBOSE=1 ;;
    --help | -h)
      sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "${arg}" >&2
      printf 'Try %s --help\n' "$0" >&2
      exit 2
      ;;
  esac
done

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
export PYCRAFT_VERBOSE

log_open start
require_repo_root || exit 1

# Failures during startup leave the stack in whatever state it reached, which is
# the most useful thing to inspect — so do not tear it down on the way out.
FAILED_STEP=""
fail_at() {
  FAILED_STEP="$1"
  fail "$1"
}

rule
printf '%s%sPyCraft — starting the platform%s\n' "${C_BOLD}" "${C_MAGENTA}" "${C_RESET}"
printf '%s  log: %s%s\n' "${C_DIM}" "${PYCRAFT_LOG_FILE:-none}" "${C_RESET}"
rule
load_env_file

# =============================================================================
# 1. Preflight
# =============================================================================
step "Preflight checks"

# --- Docker CLI ---
if ! command -v docker >/dev/null 2>&1; then
  fail_at "Docker is not installed, or is not on PATH"
  printf '\n  Install Docker Desktop or colima, then try again.\n'
  exit 1
fi
ok "Docker CLI: $(docker --version 2>/dev/null | cut -d, -f1)"

# --- Compose CLI ---
if ! resolve_compose; then
  fail_at "Neither 'docker compose' nor 'docker-compose' works"
  printf '\n  Install the Compose plugin (Docker Desktop bundles it).\n'
  printf '  Homebrew: brew install docker-compose\n'
  exit 1
fi
if [ "${COMPOSE_CMD}" = "docker-compose" ]; then
  ok "Compose: $(docker-compose version --short 2>/dev/null) (standalone binary)"
  debug "'docker compose' is unavailable; the standalone binary is used instead"
else
  ok "Compose: $(docker compose version --short 2>/dev/null) (CLI plugin)"
fi

# --- Daemon ---
# Checked before anything else touches it, because every later command would
# otherwise fail with a confusing transport error.
if ! docker info >/dev/null 2>&1; then
  fail_at "The Docker daemon is not responding"
  printf '\n'
  if command -v colima >/dev/null 2>&1; then
    printf '  colima is installed. Check it with:\n'
    printf '      colima status\n'
    printf '  and start it with:\n'
    printf '      colima start\n'
  else
    printf '  Start Docker Desktop, or the Docker daemon, then try again.\n'
  fi
  exit 1
fi
DOCKER_SERVER="$(docker info --format '{{.ServerVersion}}' 2>/dev/null || echo '?')"
DOCKER_STORAGE="$(docker info --format '{{.Driver}}' 2>/dev/null || echo '?')"
DOCKER_CPUS="$(docker info --format '{{.NCPU}}' 2>/dev/null || echo '?')"
# Docker's template language has no float division, so read the byte count and
# convert in the shell.
DOCKER_MEM_BYTES="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo '0')"
case "${DOCKER_MEM_BYTES}" in
  '' | *[!0-9]*) DOCKER_MEM_GB="?" ;;
  *) DOCKER_MEM_GB=$(( DOCKER_MEM_BYTES / 1073741824 )) ;;
esac
ok "Daemon: ${DOCKER_SERVER} (storage ${DOCKER_STORAGE}, ${DOCKER_CPUS} CPUs, ${DOCKER_MEM_GB} GiB)"

# Warn when the VM is too small to hold the stack plus sandboxes. It is a
# warning, not an error: a small daemon usually still works, just slowly.
if [ "${DOCKER_MEM_GB}" != "?" ] && [ "${DOCKER_MEM_GB}" -lt 4 ]; then
  warn "Only ${DOCKER_MEM_GB} GiB available to Docker — builds may be slow or OOM"
fi

# --- Docker socket ---
# The API mounts this so it can spawn sandboxes. The path is daemon-side, so it
# is checked by asking the daemon to mount it rather than by looking on the
# host — see resolve_docker_socket for why those differ.
DOCKER_SOCK="$(resolve_docker_socket)"
export PYCRAFT_DOCKER_SOCK="${DOCKER_SOCK}"

RUNNER_IMAGE_FOR_CHECK="${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12}"
if ! docker image inspect "${RUNNER_IMAGE_FOR_CHECK}" >/dev/null 2>&1; then
  # The checks below need an image to run in. On a first run none exists yet, so
  # skip them and rely on the post-start verification to catch a real problem.
  debug "socket checks deferred: ${RUNNER_IMAGE_FOR_CHECK} not built yet"
  ok "Docker socket: ${DOCKER_SOCK} (will be verified after the sandbox image is built)"
else
  if check_docker_socket_mountable "${DOCKER_SOCK}"; then
    ok "Docker socket: ${DOCKER_SOCK} (mounted successfully by the daemon)"
  else
    fail_at "The daemon cannot mount ${DOCKER_SOCK} into a container"
    printf '\n  The API would start but be unable to spawn execution sandboxes.\n'
    printf '  This usually means the path is host-side rather than daemon-side.\n'
    printf '  Override it with PYCRAFT_DOCKER_SOCK if the daemon is remote.\n'
    exit 1
  fi

  # Mounting is not enough: the API runs unprivileged, and the socket is mode
  # 660 owned by the daemon's group. If that group is not joined, every
  # connection is refused and submissions fail with "execution backend is not
  # available" while the container itself still reports healthy. Check the real
  # thing — a connection from the API's own user — rather than the file mode.
  DOCKER_GID="$(resolve_docker_gid)"
  export PYCRAFT_DOCKER_GID="${DOCKER_GID}"
  debug "docker socket group id: ${DOCKER_GID}"

  if check_socket_connectable "${DOCKER_SOCK}" "${DOCKER_GID}"; then
    ok "Docker socket is usable by the API's user (group ${DOCKER_GID})"
  else
    fail_at "The API's user cannot connect to the Docker socket"
    printf '\n  The socket is owned by group %s with mode 660, and the API runs\n' "${DOCKER_GID}"
    printf '  unprivileged. Without joining that group, submissions would fail\n'
    printf '  with "Execution backend is not available".\n'
    printf '\n  Override the group with PYCRAFT_DOCKER_GID if this is wrong.\n'
    exit 1
  fi
fi

# --- Source tree ---
for path in backend/pyproject.toml frontend/package.json runner/Dockerfile challenges docker-compose.yml; do
  if [ ! -e "${ROOT_DIR}/${path}" ]; then
    fail_at "Missing ${path} — the repository looks incomplete"
    exit 1
  fi
done
CHALLENGE_COUNT="$(find "${ROOT_DIR}/challenges" -mindepth 3 -maxdepth 3 -name metadata.json 2>/dev/null | wc -l | tr -d ' ')"
ok "Source tree complete (${CHALLENGE_COUNT} challenges on disk)"

# --- Free disk space ---
# Building three images plus the Postgres volume needs a few GB. Checked because
# Docker's own "no space left on device" arrives late and is hard to read.
AVAIL_KB="$(df -Pk "${ROOT_DIR}" 2>/dev/null | awk 'NR==2 {print $4}')"
if [ -n "${AVAIL_KB:-}" ]; then
  AVAIL_GB=$(( AVAIL_KB / 1048576 ))
  if [ "${AVAIL_GB}" -lt 5 ]; then
    warn "Only ${AVAIL_GB} GiB free on the volume holding the repository"
  else
    debug "free space: ${AVAIL_GB} GiB"
  fi
fi

# --- Ports ---
# Resolve the ports compose will actually publish, so an override in .env is
# respected and this check cannot disagree with what gets started.
API_PORT="$(compose_host_port api 8000 8000)"
WEB_PORT="$(compose_host_port web 80 5173)"
PG_PORT="$(compose_host_port postgres 5432 5433)"
REDIS_PORT="$(compose_host_port redis 6379 6379)"

# --- Our own stack? ---
# A previous run of *this project* is not a conflict — it is something to reuse
# or replace. Identify it by the compose project label, so this can never
# mistake another project's containers for ours.
OUR_CONTAINERS="$(docker ps -a --filter "label=com.docker.compose.project=pycraft" --format '{{.Names}}' 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')"
OUR_RUNNING="$(docker ps --filter "label=com.docker.compose.project=pycraft" --format '{{.Names}}' 2>/dev/null | tr '\n' ' ' | sed 's/ *$//')"

if [ -n "${OUR_RUNNING}" ]; then
  warn "A PyCraft stack is already running: ${OUR_RUNNING}"
  if [ -n "${OUR_CONTAINERS}" ]; then
    debug "all pycraft containers (incl. stopped): ${OUR_CONTAINERS}"
  fi
  if [ "${RECREATE}" = "1" ]; then
    step "Replacing the running stack (--recreate)"
  elif compose ps --status running --format '{{.Service}}' 2>/dev/null | grep -q .; then
    info "Reusing it — this will rebuild changed images and restart what needs it"
  fi
fi

# --- Port conflicts from *other* processes ---
# Only a real LISTEN counts. A browser holding a dead socket to a closed port
# shows up in lsof but is not a conflict, and killing it would be wrong.
CONFLICTS=""
PORT_OVERRIDES=""
check_port() {
  local port="$1" name="$2" owner="$3"
  if port_in_use "${port}"; then
    local who; who="$(who_is_on_port "${port}")"
    warn "Port ${port} (${name}) is already in use by ${who}"
    CONFLICTS="${CONFLICTS} ${name}:${port}"
    log_to_file "port conflict: ${name} ${port} held by ${who}"
    return 0
  fi
  debug "port ${port} (${name}) is free"
  return 1
}

# A port our own stack already publishes is expected when reusing it.
claims_port() {
  compose ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${1}->"
}


for spec in "${PG_PORT}:PostgreSQL:postgres" "${REDIS_PORT}:Redis:redis" \
            "${API_PORT}:API:api" "${WEB_PORT}:Web:web"; do
  p="${spec%%:*}"; rest="${spec#*:}"; n="${rest%%:*}"
  if claims_port "${p}"; then
    debug "port ${p} (${n}) is published by our own running stack"
    continue
  fi
  # Give a lingering Docker forwarder from a just-stopped container a moment to
  # let go, instead of reporting a conflict with ourselves.
  if port_in_use "${p}" && is_docker_forwarder "${p}"; then
    if wait_for_forwarder_release "${p}"; then
      debug "port ${p} (${n}) became free after the forwarder released it"
    fi
  fi
  check_port "${p}" "${n}" "" || true
done

# When a port is taken, move ours rather than failing — but only with
# --force-port, because silently running on a different port than the one in the
# docs is its own kind of confusing.
if [ -n "${CONFLICTS}" ]; then
  if [ "${FORCE_PORT}" != "1" ]; then
    printf '\n'
    fail_at "Ports already in use:${CONFLICTS}"
    cat <<'EOF'

  Options:
    ./scripts/start.sh --force-port   # move PyCraft's ports to free ones
    ./scripts/stop.sh                 # stop a PyCraft stack you left running

  Or free the port yourself. To see what holds it:
    lsof -nP -i :<port> -sTCP:LISTEN
EOF
    exit 1
  fi
  info "Moving conflicting ports to free ones (--force-port)"
  try_override() {
    local port="$1" var="$2" name="$3"
    if port_in_use "${port}"; then
      local free; free="$(find_free_port "$(( port + 1 ))")" || {
        fail_at "No free port near ${port} for ${name}"
        exit 1
      }
      warn "${name}: ${port} is taken, using ${free}"
      PORT_OVERRIDES="${PORT_OVERRIDES}${var}=${free} "
      eval "export ${var}=${free}"
    fi
  }
  try_override "${PG_PORT}" PYCRAFT_POSTGRES_PORT PostgreSQL
  try_override "${REDIS_PORT}" PYCRAFT_REDIS_PORT Redis
  try_override "${API_PORT}" PYCRAFT_API_PORT API
  try_override "${WEB_PORT}" PYCRAFT_WEB_PORT Web

  # Re-resolve: the values above are what the rest of the script reports.
  API_PORT="$(compose_host_port api 8000 8000)"
  WEB_PORT="$(compose_host_port web 80 5173)"
  ok "Ports: API ${API_PORT}, web ${WEB_PORT}"
else
  ok "Ports free: API ${API_PORT}, web ${WEB_PORT}, PostgreSQL ${PG_PORT}, Redis ${REDIS_PORT}"
fi

# =============================================================================
# 2. Build
# =============================================================================
COMPOSE_FLAGS=""
[ "${RECREATE}" = "1" ] && COMPOSE_FLAGS="${COMPOSE_FLAGS} --force-recreate"
[ "${FOREGROUND}" = "1" ] && COMPOSE_FLAGS="${COMPOSE_FLAGS} -d" || COMPOSE_FLAGS="${COMPOSE_FLAGS} -d"

if [ "${SKIP_BUILD}" = "1" ]; then
  step "Build — skipped (--no-build)"
else
  step "Building images"
  info "First build takes a few minutes; later builds reuse cached layers"

  # Build output is hundreds of lines of layer hashes. Stream it through a
  # filter so progress is still visible while a minutes-long build runs, keep
  # the complete output in a file, and dump that file if the build fails — at
  # which point the detail is exactly what is needed.
  BUILD_LOG="${LOG_DIR}/build.log"

  build_images() {
    local label="$1"; shift
    local status
    BUILD_START="$(date +%s)"
    log_to_file "\$ compose build $*"
    # `tee` keeps the full output; the filter decides what reaches the terminal.
    #
    # PIPESTATUS[0] must be read immediately, with nothing in between: any other
    # command — including a trailing `|| true` — resets it, and the build would
    # then be reported as succeeding no matter what compose did.
    compose build "$@" 2>&1 | tee "${BUILD_LOG}" | grep -E \
      '^(#[0-9]+ (DONE|ERROR|CANCELED)|ERROR|error:|failed|Successfully|=> => )'
    status=${PIPESTATUS[0]}
    _log_raw "--- compose build $* output ---"
    _log_raw "$(cat "${BUILD_LOG}" 2>/dev/null)"
    if [ "${status}" -ne 0 ]; then
      fail_at "Failed to build: ${label}"
      printf '\n  Every line of the build is in %s\n' "${BUILD_LOG}"
      printf '  The tail of it:\n'
      tail -30 "${BUILD_LOG}" 2>/dev/null | indent
      return 1
    fi
    ok "${label} ready ($(( $(date +%s) - BUILD_START ))s)"
    return 0
  }

  # The runner image is the sandbox every submission executes in, and the API's
  # `depends_on` waits for it — so a failure here is reported plainly instead of
  # surfacing later as an API startup error.
  build_images "Sandbox image" runner-image || exit 1
  build_images "API and web images" api web || exit 1
fi

# =============================================================================
# 3. Start
# =============================================================================
step "Starting services"
START_FLAGS="-d"
[ "${RECREATE}" = "1" ] && START_FLAGS="${START_FLAGS} --force-recreate"

# `up` is run with the port overrides in the environment so compose interpolates
# the same values the preflight resolved.
#
# Output is filtered rather than shown raw: pulling layers and creating the
# network is dozens of lines that say nothing useful once it has worked, and
# they bury the one line that matters when it does not.
log_to_file "\$ compose up ${START_FLAGS}"
compose up ${START_FLAGS} --quiet-pull 2>&1 | tee "${LOG_DIR}/up.log" | grep -E \
  'Error|error|ERROR|failed|Failed|Started|Healthy|Created|warning|Warning'
UP_STATUS=${PIPESTATUS[0]}
_log_raw "$(cat "${LOG_DIR}/up.log" 2>/dev/null)"
if [ "${UP_STATUS}" -ne 0 ]; then
  fail_at "docker compose up failed"
  printf '\n  The tail of the output:\n'
  tail -25 "${LOG_DIR}/up.log" 2>/dev/null | indent
  printf '\n  Full output: %s\n' "${LOG_DIR}/up.log"
  exit 1
fi
ok "Containers created and started"

# --- Wait for each service, in dependency order ------------------------------
step "Waiting for services to become healthy"

wait_for_container_health() {
  local service="$1" label="$2" attempts="${3:-60}"
  local i=1 cid state health
  while [ "${i}" -le "${attempts}" ]; do
    cid="$(compose ps -q "${service}" 2>/dev/null | head -1)"
    if [ -z "${cid}" ]; then
      if [ "${i}" -eq "${attempts}" ]; then
        fail_at "${label}: container never appeared"
        return 1
      fi
      sleep 2; i=$(( i + 1 )); continue
    fi
    state="$(docker inspect -f '{{.State.Status}}' "${cid}" 2>/dev/null || echo unknown)"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${cid}" 2>/dev/null || echo none)"
    debug "${label}: state=${state} health=${health} (attempt ${i}/${attempts})"

    case "${state}" in
      exited | dead)
        fail_at "${label}: container ${state}"
        docker logs --tail 40 "${cid}" 2>&1 | indent
        return 1
        ;;
    esac

    if [ "${health}" = "healthy" ] || { [ "${health}" = "none" ] && [ "${state}" = "running" ]; }; then
      ok "${label} is ${health/none/running}"
      return 0
    fi
    if [ "${health}" = "unhealthy" ]; then
      fail_at "${label}: container is unhealthy"
      docker logs --tail 40 "${cid}" 2>&1 | indent
      return 1
    fi
    sleep 2; i=$(( i + 1 ))
  done
  fail_at "${label}: timed out waiting to become healthy"
  return 1
}

wait_for_container_health postgres "PostgreSQL" 60 || exit 1
wait_for_container_health redis "Redis" 40 || exit 1

# The runner-image service builds and exits on purpose; wait for that exit
# rather than for a health status it never reports.
RI_CID="$(compose ps -aq runner-image 2>/dev/null | head -1)"
if [ -n "${RI_CID}" ]; then
  RI_STATE="$(docker inspect -f '{{.State.Status}}/{{.State.ExitCode}}' "${RI_CID}" 2>/dev/null || echo '?')"
  case "${RI_STATE}" in
    exited/0) ok "Sandbox image present" ;;
    *)        warn "runner-image container finished as ${RI_STATE} (harmless if the image exists)" ;;
  esac
fi
if docker image inspect "${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12}" >/dev/null 2>&1; then
  ok "Sandbox image ${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12} is available to the daemon"
else
  fail_at "Sandbox image ${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12} is missing"
  exit 1
fi

wait_for_container_health api "API" 90 || exit 1

# =============================================================================
# 4. Verify
# =============================================================================
step "Verifying the API is really working"

API_URL="http://127.0.0.1:${API_PORT}"

# `/health` only proves the process is up. `/runtime` proves the lifespan
# finished — it has read the catalogue and created the execution backend — which
# is what "ready to accept a submission" actually means.
if ! wait_for_http "${API_URL}/api/v1/runtime" 30 2 "runtime"; then
  fail_at "The API never answered ${API_URL}/api/v1/runtime"
  printf '\n  Last 40 lines from the API:\n'
  compose logs --tail 40 api 2>&1 | indent
  exit 1
fi

RUNTIME_JSON="$(http_get "${API_URL}/api/v1/runtime" || echo '')"
if [ -n "${RUNTIME_JSON}" ]; then
  EXEC_BACKEND="$(printf '%s' "${RUNTIME_JSON}" | jq -r '.execution_backend // "?"' 2>/dev/null)"
  CHALLENGES_LOADED="$(printf '%s' "${RUNTIME_JSON}" | jq -r '.challenge_count // "?"' 2>/dev/null)"
  PY_VERSION="$(printf '%s' "${RUNTIME_JSON}" | jq -r '.default_python_version // "?"' 2>/dev/null)"
  ENVIRONMENT="$(printf '%s' "${RUNTIME_JSON}" | jq -r '.environment // "?"' 2>/dev/null)"
  ok "API ready — ${CHALLENGES_LOADED} challenges indexed, Python ${PY_VERSION}, env ${ENVIRONMENT}"

  # The whole point of the platform is executing code safely. If the backend is
  # not the sandbox, say so loudly rather than letting a learner discover it.
  if [ "${EXEC_BACKEND}" = "docker" ]; then
    ok "Execution backend: docker (sandboxed)"
  else
    warn "Execution backend is '${EXEC_BACKEND}', NOT 'docker' — code is not sandboxed!"
  fi
  if [ "${CHALLENGES_LOADED}" != "?" ] && [ "${CHALLENGES_LOADED}" != "${CHALLENGE_COUNT}" ]; then
    warn "Indexed ${CHALLENGES_LOADED} challenges but ${CHALLENGE_COUNT} are on disk"
  fi
fi

# Queue depth proves the workers are alive. They drain the submission queue; if
# they are not running, submissions queue up and never execute.
QUEUE_JSON="$(http_get "${API_URL}/api/v1/queue" || echo '')"
if [ -n "${QUEUE_JSON}" ]; then
  WAITING="$(printf '%s' "${QUEUE_JSON}" | jq -r '.waiting // 0' 2>/dev/null)"
  RUNNING="$(printf '%s' "${QUEUE_JSON}" | jq -r '.in_flight // 0' 2>/dev/null)"
  WORKERS="$(printf '%s' "${QUEUE_JSON}" | jq -r '.workers // "?"' 2>/dev/null)"
  ok "Queue: ${WAITING} waiting, ${RUNNING} running, ${WORKERS} worker(s)"
fi

if ! wait_for_http "http://127.0.0.1:${WEB_PORT}/" 30 2 "web"; then
  fail_at "The web UI never answered on http://127.0.0.1:${WEB_PORT}/"
  compose logs --tail 40 web 2>&1 | indent
  exit 1
fi
ok "Web UI is serving on http://127.0.0.1:${WEB_PORT}/"

# The end-to-end check: a browser loads the SPA and the SPA calls the API through
# nginx. Checking the proxy path catches a misconfigured `proxy_pass`, which a
# plain page load would not.
PROXIED="$(http_get "http://127.0.0.1:${WEB_PORT}/api/v1/runtime" || echo '')"
if [ -n "${PROXIED}" ]; then
  ok "Web → API proxy works (/api/v1/runtime through nginx)"
else
  warn "The web UI could not reach the API through its own proxy"
fi

# A real graded submission, which exercises the sandbox — the one path that
# nothing above proves. Skippable because it is the slowest step.
if [ "${NO_VERIFY}" = "0" ]; then
  step "End-to-end check: registering a user and grading a submission"

  VERIFY_EMAIL="smoke-$(date +%s)@example.com"
  VERIFY_PASS="Smoke-Test-2026"

  REGISTER_BODY="$(jq -n --arg e "${VERIFY_EMAIL}" --arg p "${VERIFY_PASS}" --arg d "Smoke Test" \
    '{email: $e, password: $p, display_name: $d}')"

  REGISTER_RESPONSE="$(curl -sS --max-time 20 -w '\n%{http_code}' \
    -X POST "${API_URL}/api/v1/auth/register" \
    -H 'Content-Type: application/json' \
    -d "${REGISTER_BODY}" 2>/dev/null || echo '000')"
  REGISTER_CODE="$(printf '%s' "${REGISTER_RESPONSE}" | tail -1)"
  REGISTER_JSON="$(printf '%s' "${REGISTER_RESPONSE}" | sed '$d')"

  if [ "${REGISTER_CODE}" != "201" ] && [ "${REGISTER_CODE}" != "200" ]; then
    fail_at "Could not register a test user (HTTP ${REGISTER_CODE})"
    printf '%s\n' "${REGISTER_JSON}" | head -5 | indent
    warn "Skipping the submission check — the API is up but registration failed"
  else
    TOKEN="$(printf '%s' "${REGISTER_JSON}" | jq -r '.access_token // empty' 2>/dev/null)"
    if [ -z "${TOKEN}" ]; then
      fail_at "Registration succeeded but returned no token"
    else
      ok "Registered ${VERIFY_EMAIL}"

      # Submit the correct solution to Hello World, so a pass proves the whole
      # chain: auth → queue → worker → sandbox → grading → progress.
      SOLUTION='{"files": {"solution.py": "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n"}}'
      SUBMIT_RESPONSE="$(curl -sS --max-time 20 -w '\n%{http_code}' \
        -X POST "${API_URL}/api/v1/challenges/python-fundamentals-hello-world/submit" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer ${TOKEN}" \
        -d "${SOLUTION}" 2>/dev/null || echo '000')"
      SUBMIT_CODE="$(printf '%s' "${SUBMIT_RESPONSE}" | tail -1)"
      SUBMIT_JSON="$(printf '%s' "${SUBMIT_RESPONSE}" | sed '$d')"

      if [ "${SUBMIT_CODE}" != "202" ]; then
        fail_at "Submitting returned HTTP ${SUBMIT_CODE} (expected 202)"
        printf '%s\n' "${SUBMIT_JSON}" | head -5 | indent
      else
        SUBMISSION_ID="$(printf '%s' "${SUBMIT_JSON}" | jq -r '.submission_id // empty')"
        ok "Submission queued (202) — id ${SUBMISSION_ID}"

        # Poll until the worker finishes. The lease is 120s and the sandbox
        # takes seconds, so 60 attempts is generous without being unbounded.
        POLL=0
        MAX_POLLS=60
        FINAL_JSON=""
        while [ "${POLL}" -lt "${MAX_POLLS}" ]; do
          POLL=$(( POLL + 1 ))
          FINAL_JSON="$(curl -sS --max-time 10 \
            -H "Authorization: Bearer ${TOKEN}" \
            "${API_URL}/api/v1/submissions/${SUBMISSION_ID}" 2>/dev/null || echo '')"
          DONE="$(printf '%s' "${FINAL_JSON}" | jq -r '.done // false' 2>/dev/null)"
          if [ "${DONE}" = "true" ]; then break; fi
          sleep 2
        done

        STATUS="$(printf '%s' "${FINAL_JSON}" | jq -r '.status // "?"' 2>/dev/null)"
        if [ "${DONE}" != "true" ]; then
          fail_at "The submission never finished (status ${STATUS} after $(( MAX_POLLS * 2 ))s)"
          printf '\n  The queue accepted it but no worker completed it. Check:\n'
          printf '      ./scripts/logs.sh api\n'
          printf '      curl -s %s/api/v1/queue | jq\n' "${API_URL}"
        else
          SCORE="$(printf '%s' "${FINAL_JSON}" | jq -r '.score // "?"' 2>/dev/null)"
          PASSED="$(printf '%s' "${FINAL_JSON}" | jq -r '.passed // "?"' 2>/dev/null)"
          TOTAL="$(printf '%s' "${FINAL_JSON}" | jq -r '.total_tests // "?"' 2>/dev/null)"
          ok "Submission graded — status ${STATUS}, score ${SCORE}, tests ${PASSED}/${TOTAL}"

          if [ "${SCORE}" = "100" ]; then
            ok "Sandbox executed learner code and scored it correctly"
          else
            warn "Expected a score of 100 for the reference solution, got ${SCORE}"
            warn "The platform is running, but grading may be misconfigured"
          fi
        fi
      fi
    fi
  fi
else
  skip "End-to-end submission check (--no-verify)"
fi

# =============================================================================
# Done
# =============================================================================
rule
if [ -n "${FAILED_STEP}" ]; then
  printf '%s%sPyCraft started, but a check failed:%s %s\n' "${C_BOLD}" "${C_YELLOW}" "${C_RESET}" "${FAILED_STEP}"
  rule
  exit 1
fi

printf '%s%sPyCraft is running%s\n' "${C_BOLD}" "${C_GREEN}" "${C_RESET}"
rule
printf '  %sWeb UI%s      http://127.0.0.1:%s\n' "${C_BOLD}" "${C_RESET}" "${WEB_PORT}"
printf '  %sAPI%s         http://127.0.0.1:%s/api/v1\n' "${C_BOLD}" "${C_RESET}" "${API_PORT}"
printf '  %sAPI docs%s    http://127.0.0.1:%s/docs\n' "${C_BOLD}" "${C_RESET}" "${API_PORT}"
printf '  %sLogs%s        ./scripts/logs.sh <postgres|redis|api|web>\n' "${C_BOLD}" "${C_RESET}"
printf '  %sStatus%s      ./scripts/status.sh\n' "${C_BOLD}" "${C_RESET}"
printf '  %sStop%s        ./scripts/stop.sh\n' "${C_BOLD}" "${C_RESET}"
printf '\n  %sThis run log: %s%s\n\n' "${C_DIM}" "${PYCRAFT_LOG_FILE:-none}" "${C_RESET}"

log_to_file "start complete: web=${WEB_PORT} api=${API_PORT}"

if [ "${FOREGROUND}" = "1" ]; then
  rule
  info "Following logs — press Ctrl-C to stop watching (containers keep running)"
  exec compose logs -f --tail 50
fi

exit 0
