#!/usr/bin/env bash
#
# Show what the PyCraft platform is doing right now.
#
#   ./scripts/status.sh            # containers, endpoints, queue, data
#   ./scripts/status.sh --watch    # refresh every few seconds
#   ./scripts/status.sh --json     # machine-readable summary
#
# Designed to answer "is it healthy?" in one screen: container states, whether
# the API and web UI actually respond, how deep the submission queue is, and how
# much data is in the database. It never changes anything.

WATCH=0
AS_JSON=0
INTERVAL="${PYCRAFT_WATCH_INTERVAL:-5}"
for arg in "$@"; do
  case "${arg}" in
    --watch | -w) WATCH=1 ;;
    --json)       AS_JSON=1 ;;
    --verbose)    PYCRAFT_VERBOSE=1 ;;
    --help | -h)  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'Unknown option: %s\n' "${arg}" >&2; exit 2 ;;
  esac
done

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
export PYCRAFT_VERBOSE

log_open status
require_repo_root || exit 1
load_env_file

# Collected as we go so --json can print the whole picture at the end.
STATUS_CONTAINERS="unknown"
STATUS_API="down"
STATUS_WEB="down"
STATUS_BACKEND="unknown"
STATUS_CHALLENGES="0"
STATUS_QUEUE="?"
STATUS_USERS="?"
STATUS_SUBMISSIONS="?"

read_counts() {
  # Read the row counts straight from PostgreSQL, which answers "is there really
  # data?" far more convincingly than "the container is running".
  local cid
  cid="$(compose ps -q postgres 2>/dev/null | head -1)"
  [ -n "${cid}" ] || return 0

  local state
  state="$(docker inspect -f '{{.State.Status}}' "${cid}" 2>/dev/null || echo unknown)"
  [ "${state}" = "running" ] || return 0

  local counts
  counts="$(docker exec "${cid}" psql -U pycraft -d pycraft -tAc \
    "select (select count(*) from users), (select count(*) from submissions), (select count(*) from challenges)" \
    2>/dev/null || true)"
  if [ -n "${counts}" ]; then
    STATUS_USERS="$(printf '%s' "${counts}" | cut -d'|' -f1 | tr -d ' ')"
    STATUS_SUBMISSIONS="$(printf '%s' "${counts}" | cut -d'|' -f2 | tr -d ' ')"
    STATUS_CHALLENGES="$(printf '%s' "${counts}" | cut -d'|' -f3 | tr -d ' ')"
    debug "db counts: users=${STATUS_USERS} submissions=${STATUS_SUBMISSIONS} challenges=${STATUS_CHALLENGES}"
  fi
}

collect() {
  # --- Containers ---
  if ! docker info >/dev/null 2>&1; then
    STATUS_CONTAINERS="daemon-down"
    return 0
  fi
  local ids
  ids="$(docker ps -aq --filter "label=com.docker.compose.project=pycraft" 2>/dev/null || true)"
  if [ -z "${ids}" ]; then
    STATUS_CONTAINERS="absent"
    return 0
  fi
  STATUS_CONTAINERS="present"

  # --- API readiness ---
  local api_port
  api_port="$(compose_host_port api 8000 8000)"
  local api_url="http://127.0.0.1:${api_port}"
  local runtime
  runtime="$(http_get "${api_url}/api/v1/runtime" || true)"
  if [ -n "${runtime}" ]; then
    STATUS_API="up"
    STATUS_BACKEND="$(printf '%s' "${runtime}" | jq -r '.execution_backend // "?"' 2>/dev/null)"
    STATUS_CHALLENGES="$(printf '%s' "${runtime}" | jq -r '.challenge_count // "?"' 2>/dev/null)"
  elif [ "$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "${api_url}/health" 2>/dev/null || echo 000)" != "000" ]; then
    # The process answers but /runtime does not: startup did not finish.
    STATUS_API="starting"
  fi

  # --- Queue ---
  local queue
  queue="$(http_get "${api_url}/api/v1/queue" || true)"
  if [ -n "${queue}" ]; then
    STATUS_QUEUE="$(printf '%s' "${queue}" | jq -r '"\(.waiting // 0) waiting / \(.in_flight // 0) running / \(.workers // "?") workers"' 2>/dev/null)"
  fi

  # --- Web ---
  local web_port
  web_port="$(compose_host_port web 80 5173)"
  if curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:${web_port}/" 2>/dev/null; then
    STATUS_WEB="up"
  fi

  read_counts
}

render() {
  rule
  printf '%s%sPyCraft status%s  %s\n' "${C_BOLD}" "${C_CYAN}" "${C_RESET}" "$(date '+%H:%M:%S')"
  rule

  # --- Containers ---
  step "Containers"
  if ! docker info >/dev/null 2>&1; then
    fail "Docker daemon is not reachable"
  elif [ "${STATUS_CONTAINERS}" = "absent" ]; then
    warn "No PyCraft containers exist — the platform is not running"
    info "Start it with ./scripts/start.sh"
  else
    # `docker compose ps` lays the table out already; reuse it rather than
    # reimplementing a worse version.
    compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null | indent
  fi

  # --- Endpoints ---
  printf '\n'
  step "Endpoints"
  local api_port web_port
  api_port="$(compose_host_port api 8000 8000)"
  web_port="$(compose_host_port web 80 5173)"

  case "${STATUS_API}" in
    up)
      ok "API      http://127.0.0.1:${api_port}/api/v1  (${STATUS_CHALLENGES} challenges indexed)"
      ;;
    starting)
      warn "API      http://127.0.0.1:${api_port}  (responding, still starting up)"
      ;;
    *)
      if [ "${STATUS_CONTAINERS}" = "absent" ]; then
        skip "API      not running"
      else
        fail "API      http://127.0.0.1:${api_port}  is not responding"
      fi
      ;;
  esac

  case "${STATUS_WEB}" in
    up) ok "Web UI   http://127.0.0.1:${web_port}/" ;;
    *)  [ "${STATUS_CONTAINERS}" = "absent" ] && skip "Web UI   not running" \
        || fail "Web UI   http://127.0.0.1:${web_port}/  is not responding" ;;
  esac

  # --- Execution ---
  if [ "${STATUS_BACKEND}" != "unknown" ]; then
    printf '\n'
    step "Execution"
    if [ "${STATUS_BACKEND}" = "docker" ]; then
      ok "Sandbox backend: docker"
      local runner_image="${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12}"
      if docker image inspect "${runner_image}" >/dev/null 2>&1; then
        ok "Sandbox image ${runner_image} present"
      else
        fail "Sandbox image ${runner_image} is MISSING — submissions will fail"
      fi
      # A mounted socket is not the same as a usable one: the API runs
      # unprivileged and the socket is group-owned, so this is the check that
      # explains "Execution backend is not available" when the API looks healthy.
      local sock gid
      sock="$(resolve_docker_socket)"
      gid="$(resolve_docker_gid)"
      if check_socket_connectable "${sock}" "${gid}"; then
        ok "API can reach the Docker socket (group ${gid})"
      else
        fail "The API CANNOT reach the Docker socket — submissions will fail"
        info "Socket ${sock} is owned by group ${gid}; the API runs unprivileged"
      fi
      local sandboxes
      sandboxes="$(docker ps -q --filter "label=pycraft-runner" 2>/dev/null | wc -l | tr -d ' ')"
      info "Sandbox containers running right now: ${sandboxes}"
    else
      warn "Sandbox backend is '${STATUS_BACKEND}', not 'docker' — code is NOT isolated"
    fi
  fi

  # --- Queue ---
  if [ "${STATUS_QUEUE}" != "?" ]; then
    printf '\n'
    step "Submission queue"
    info "${STATUS_QUEUE}"
  fi

  # --- Data ---
  if [ "${STATUS_USERS}" != "?" ]; then
    printf '\n'
    step "Data"
    info "Users: ${STATUS_USERS}   Challenges: ${STATUS_CHALLENGES}   Submissions: ${STATUS_SUBMISSIONS}"
  elif [ "${STATUS_CONTAINERS}" != "absent" ]; then
    printf '\n'
    step "Data"
    skip "Could not read row counts (PostgreSQL may still be starting)"
  fi
  printf '\n'
}

if [ "${AS_JSON}" = "1" ]; then
  collect
  jq -n \
    --arg containers "${STATUS_CONTAINERS}" \
    --arg api "${STATUS_API}" \
    --arg web "${STATUS_WEB}" \
    --arg backend "${STATUS_BACKEND}" \
    --arg challenges "${STATUS_CHALLENGES}" \
    --arg queue "${STATUS_QUEUE}" \
    --arg users "${STATUS_USERS}" \
    --arg submissions "${STATUS_SUBMISSIONS}" \
    '{containers: $containers, api: $api, web: $web, execution_backend: $backend,
      challenges: $challenges, queue: $queue, users: $users, submissions: $submissions}'
  # Health is a status, so the exit code reflects it.
  [ "${STATUS_API}" = "up" ] && exit 0 || exit 1
fi

if [ "${WATCH}" = "1" ]; then
  info "Watching every ${INTERVAL}s — press Ctrl-C to stop"
  while true; do
    collect
    # Clear the screen between frames so the display does not scroll away.
    # Only do this on a real terminal; in a pipe it would emit escape codes.
    [ -t 1 ] && printf '\033[H\033[2J'
    render
    sleep "${INTERVAL}"
  done
else
  collect
  render
fi

[ "${STATUS_API}" = "up" ] && exit 0 || exit 1
