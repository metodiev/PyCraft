#!/usr/bin/env bash
#
# Stop the PyCraft platform.
#
#   ./scripts/stop.sh              # stop containers, keep data and images
#   ./scripts/stop.sh --volumes    # also delete the database and queue volumes
#   ./scripts/stop.sh --images     # also delete PyCraft's built images
#   ./scripts/stop.sh --all        # containers, volumes and images
#   ./scripts/stop.sh --orphans    # also kill leftover non-container processes
#   ./scripts/stop.sh --yes        # no confirmation prompt
#
# Only ever touches things labelled `com.docker.compose.project=pycraft`, so it
# cannot stop another project's containers even if they share an image name.
#
# `--volumes` is destructive: it deletes the PostgreSQL data volume, so every
# account, submission and progress record is gone. It asks first.

# --- Arguments ---------------------------------------------------------------
REMOVE_VOLUMES=0
REMOVE_IMAGES=0
KILL_ORPHANS=0
ASSUME_YES=0
for arg in "$@"; do
  case "${arg}" in
    --volumes | -v) REMOVE_VOLUMES=1 ;;
    --images | -i)  REMOVE_IMAGES=1 ;;
    --orphans | -o) KILL_ORPHANS=1 ;;
    --all | -a)     REMOVE_VOLUMES=1; REMOVE_IMAGES=1; KILL_ORPHANS=1 ;;
    --yes | -y)     ASSUME_YES=1 ;;
    --verbose)      PYCRAFT_VERBOSE=1 ;;
    --help | -h)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
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

log_open stop
require_repo_root || exit 1

rule
printf '%s%sPyCraft — stopping the platform%s\n' "${C_BOLD}" "${C_YELLOW}" "${C_RESET}"
rule

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  warn "The Docker daemon is not reachable — nothing to stop"
  info "Containers may still exist; start Docker and re-run to clean them up"
  exit 0
fi

if ! resolve_compose; then
  fail "Compose is unavailable; falling back to direct Docker cleanup"
fi

# --- What is ours ------------------------------------------------------------
# Identify containers by the compose project label rather than by name, so a
# service that was renamed, or a container from another project using the same
# image, is never touched.
CONTAINER_IDS="$(docker ps -aq --filter "label=com.docker.compose.project=pycraft" 2>/dev/null || true)"
RUNNING_IDS="$(docker ps -q --filter "label=com.docker.compose.project=pycraft" 2>/dev/null || true)"

if [ -z "${CONTAINER_IDS}" ] && [ -z "${RUNNING_IDS}" ]; then
  info "No PyCraft containers are running or stopped"
else
  if [ -n "${RUNNING_IDS}" ]; then
    printf '\n'
    info "Containers currently running:"
    docker ps --filter "label=com.docker.compose.project=pycraft" \
      --format '      {{.Names}}  ({{.Status}})' 2>/dev/null
    RUNNING_COUNT="$(printf '%s\n' "${RUNNING_IDS}" | grep -c . || echo 0)"
    ok "${RUNNING_COUNT} PyCraft container(s) running"
  else
    info "No PyCraft containers are running"
  fi

  # Warn about sandboxes left behind by a crashed run. They are created by the
  # execution backend, not by compose, so they carry a different label.
  LEFTOVER_SANDBOXES="$(docker ps -aq --filter "label=pycraft-runner" 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${LEFTOVER_SANDBOXES}" != "0" ]; then
    warn "${LEFTOVER_SANDBOXES} leftover sandbox container(s) from earlier runs"
    info "These are removed below — they are ephemeral and hold no data"
  fi
fi

# --- Confirmation ------------------------------------------------------------
if [ "${REMOVE_VOLUMES}" = "1" ] && [ "${ASSUME_YES}" != "1" ]; then
  printf '\n'
  warn "This deletes the PostgreSQL data volume: every account, submission"
  warn "and progress record will be permanently lost."
  if ! confirm "Delete PyCraft's data volumes?"; then
    info "Keeping the data. Re-run without --volumes to stop but keep it."
    REMOVE_VOLUMES=0
  fi
fi

# --- Stop --------------------------------------------------------------------
step "Stopping containers"

STOP_FAILED=0
if resolve_compose; then
  # `down` removes containers and the compose network. Volumes are left alone
  # unless explicitly requested, because they hold the database.
  DOWN_FLAGS="--remove-orphans"
  [ "${REMOVE_VOLUMES}" = "1" ] && DOWN_FLAGS="${DOWN_FLAGS} --volumes"

  log_to_file "\$ compose down ${DOWN_FLAGS}"
  if compose down ${DOWN_FLAGS} 2>&1 | indent; then
    ok "Compose stack is down"
  else
    warn "compose down reported a problem; falling back to direct removal"
    STOP_FAILED=1
  fi
else
  STOP_FAILED=1
fi

# Belt and braces: if compose could not do it (a corrupt state file, a missing
# compose binary), remove the containers directly. docker rm is fixed by the
# label filter, so this still only touches PyCraft.
REMAINING="$(docker ps -aq --filter "label=com.docker.compose.project=pycraft" 2>/dev/null || true)"
if [ -n "${REMAINING}" ]; then
  step "Removing containers compose left behind"
  # shellcheck disable=SC2086 # Word splitting is intended: these are IDs.
  if docker rm -f ${REMAINING} 2>&1 | indent; then
    ok "Removed remaining PyCraft containers"
  else
    fail "Could not remove some containers"
  fi
fi

# Leftover sandboxes are ephemeral, carry no state, and are safe to force-remove.
if [ -n "${LEFTOVER_SANDBOXES:-0}" ] && [ "${LEFTOVER_SANDBOXES}" != "0" ]; then
  step "Removing leftover sandbox containers"
  SANDBOX_IDS="$(docker ps -aq --filter "label=pycraft-runner" 2>/dev/null || true)"
  if [ -n "${SANDBOX_IDS}" ]; then
    # shellcheck disable=SC2086
    docker rm -f ${SANDBOX_IDS} >/dev/null 2>&1 && ok "Sandboxes removed"
  fi
fi

# Leftover payload volumes are staged by the backend and deleted after each
# run. One surviving means a run was killed mid-flight; they are tiny, but they
# accumulate and are safe to remove once nothing is using them.
step "Checking for leftover sandbox payload volumes"
PAYLOAD_VOLUMES="$(docker volume ls -q --filter "label=pycraft=payload-staging" 2>/dev/null || true)"
if [ -n "${PAYLOAD_VOLUMES}" ]; then
  PAYLOAD_COUNT="$(printf '%s\n' "${PAYLOAD_VOLUMES}" | grep -c . || echo 0)"
  warn "${PAYLOAD_COUNT} orphaned payload volume(s) found"
  # shellcheck disable=SC2086
  if docker volume rm ${PAYLOAD_VOLUMES} >/dev/null 2>&1; then
    ok "Payload volumes removed"
  else
    warn "Some payload volumes are still in use and were left alone"
  fi
else
  ok "No orphaned payload volumes"
fi

# --- Volumes and images ------------------------------------------------------
if [ "${REMOVE_VOLUMES}" = "1" ]; then
  step "Removing data volumes"
  for vol in pycraft_postgres-data pycraft_redis-data; do
    if docker volume inspect "${vol}" >/dev/null 2>&1; then
      if docker volume rm "${vol}" >/dev/null 2>&1; then
        ok "Removed ${vol}"
      else
        fail "Could not remove ${vol} (still in use?)"
      fi
    else
      skip "${vol} does not exist"
    fi
  done
fi

if [ "${REMOVE_IMAGES}" = "1" ]; then
  step "Removing built images"
  for img in pycraft-api pycraft-web pycraft-runner:3.12; do
    if docker image inspect "${img}" >/dev/null 2>&1; then
      if docker image rm "${img}" >/dev/null 2>&1; then
        ok "Removed ${img}"
      else
        warn "${img} has dependent containers and was left in place"
      fi
    else
      skip "${img} does not exist"
    fi
  done
fi

# --- Orphans outside Docker --------------------------------------------------
# A crashed start can leave a host process holding a port — most often the
# Vite dev server or a uvicorn run started by hand. These are not containers,
# so compose knows nothing about them.
if [ "${KILL_ORPHANS}" = "1" ]; then
  step "Looking for leftover host processes on PyCraft ports"
  load_env_file
  API_PORT="$(compose_host_port api 8000 8000)"
  WEB_PORT="$(compose_host_port web 80 5173)"
  PG_PORT="$(compose_host_port postgres 5432 5433)"
  REDIS_PORT="$(compose_host_port redis 6379 6379)"

  for pair in "${WEB_PORT}:web" "${API_PORT}:api" "${PG_PORT}:PostgreSQL" "${REDIS_PORT}:Redis"; do
    port="${pair%%:*}"; label="${pair#*:}"
    if port_in_use "${port}"; then
      pid="$(lsof -nP -i "TCP:${port}" -sTCP:LISTEN -t 2>/dev/null | head -1)"
      cmd="$(ps -o command= -p "${pid}" 2>/dev/null | head -1)"
      warn "Port ${port} (${label}) still held by pid ${pid}"
      printf '      %s\n' "$(printf '%s' "${cmd}" | cut -c1-100)"

      # Only kill it if it is clearly a PyCraft process from this checkout.
      # Anything else might be unrelated work, so it is reported and left.
      if printf '%s' "${cmd}" | grep -q "${ROOT_DIR}"; then
        info "This belongs to this checkout — stopping pid ${pid}"
        kill "${pid}" 2>/dev/null || true
        sleep 1
        if kill -0 "${pid}" 2>/dev/null; then
          warn "It did not stop; leaving it alone rather than forcing"
        else
          ok "Stopped pid ${pid}"
        fi
      else
        skip "Not a process from this repository — left alone"
      fi
    fi
  done
else
  debug "orphan cleanup not requested (use --orphans)"
fi

# --- Summary -----------------------------------------------------------------
rule
if [ "${REMOVE_VOLUMES}" = "1" ]; then
  printf '%sPyCraft stopped, data deleted.%s\n' "${C_GREEN}" "${C_RESET}"
elif [ "${REMOVE_IMAGES}" = "1" ]; then
  printf '%sPyCraft stopped, images removed, data kept.%s\n' "${C_GREEN}" "${C_RESET}"
else
  printf '%sPyCraft stopped. Data and images kept.%s\n' "${C_GREEN}" "${C_RESET}"
  printf '  %sRestart with ./scripts/start.sh%s\n' "${C_DIM}" "${C_RESET}"
fi
printf '\n'
log_to_file "stop complete (volumes=${REMOVE_VOLUMES} images=${REMOVE_IMAGES})"
exit 0
