#!/usr/bin/env bash
#
# Restart the PyCraft platform, or a single service.
#
#   ./scripts/restart.sh              # stop then start everything
#   ./scripts/restart.sh api          # restart only the API
#   ./scripts/restart.sh api web      # restart several services
#   ./scripts/restart.sh --rebuild    # full stop, rebuild images, start
#
# Restarting one service is the common case while developing: the API picks up
# new challenge files, or the web container picks up a rebuilt bundle, without
# touching the database.
#
# Note that editing challenge files does NOT need a restart in the running
# stack — `challenges/` is bind-mounted read-only — but publishing one through
# the authoring UI writes to disk, and the API re-indexes on a rescan.

REBUILD=0
SERVICES=""
EXTRA=""

for arg in "$@"; do
  case "${arg}" in
    --rebuild)  REBUILD=1 ;;
    --foreground | -f) EXTRA="${EXTRA} --foreground" ;;
    --verbose)  PYCRAFT_VERBOSE=1 ;;
    --help | -h) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) printf 'Unknown option: %s\n' "${arg}" >&2; printf 'Try %s --help\n' "$0" >&2; exit 2 ;;
    *)  SERVICES="${SERVICES} ${arg}" ;;
  esac
done

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
export PYCRAFT_VERBOSE

log_open restart
require_repo_root || exit 1
load_env_file

rule
printf '%s%sPyCraft — restarting%s\n' "${C_BOLD}" "${C_MAGENTA}" "${C_RESET}"
rule

if ! resolve_compose; then
  fatal "Compose is unavailable"
  exit 1
fi

# --- Validate services -------------------------------------------------------
if [ -n "${SERVICES}" ]; then
  for svc in ${SERVICES}; do
    if ! compose config --services 2>/dev/null | grep -qx "${svc}"; then
      fail "Unknown service: ${svc}"
      printf '\nAvailable services:\n'
      compose config --services 2>/dev/null | sed 's/^/    /'
      exit 2
    fi
  done
  step "Restarting: ${SERVICES}"
  # `restart` keeps the container and its configuration, so this is fast and
  # does not disturb the database.
  log_to_file "\$ compose restart ${SERVICES}"
  if compose restart ${SERVICES} 2>&1 | indent; then
    ok "Restarted${SERVICES}"
  else
    fail "Restart failed"
    exit 1
  fi

  # Confirm the service actually came back rather than trusting `restart`.
  step "Waiting for it to be ready"
  for svc in ${SERVICES}; do
    cid="$(compose ps -q "${svc}" 2>/dev/null | head -1)"
    [ -n "${cid}" ] || { warn "${svc}: no container"; continue; }
    state="$(docker inspect -f '{{.State.Status}}' "${cid}" 2>/dev/null || echo unknown)"
    if [ "${state}" = "running" ]; then
      ok "${svc} is running"
    else
      fail "${svc} is ${state}"
      docker logs --tail 30 "${cid}" 2>&1 | indent
    fi
  done

  # A restarted API needs a moment before it answers; probe it so the caller
  # does not have to.
  if printf '%s' "${SERVICES}" | grep -qw "api"; then
    api_port="$(compose_host_port api 8000 8000)"
    if wait_for_http "http://127.0.0.1:${api_port}/api/v1/runtime" 45 2 "api"; then
      ok "API is answering again"
      runtime="$(http_get "http://127.0.0.1:${api_port}/api/v1/runtime" || true)"
      [ -n "${runtime}" ] && info "Challenges indexed: $(printf '%s' "${runtime}" | jq -r '.challenge_count // "?"' 2>/dev/null)"
    else
      fail "API did not come back up"
      compose logs --tail 40 api 2>&1 | indent
      exit 1
    fi
  fi

  rule
  printf '%sRestarted:%s%s\n\n' "${C_GREEN}" "${SERVICES}" "${C_RESET}"
  exit 0
fi

# --- Whole stack -------------------------------------------------------------
if [ "${REBUILD}" = "1" ]; then
  info "Full rebuild: stopping, rebuilding images, starting"
  # shellcheck disable=SC2086
  "${SCRIPTS_DIR}/stop.sh" --yes || true
  # shellcheck disable=SC2086
  exec "${SCRIPTS_DIR}/start.sh" --recreate ${EXTRA}
fi

step "Restarting the whole stack"
info "Containers are restarted in place; data is untouched"

log_to_file "\$ compose restart"
if compose restart 2>&1 | indent; then
  ok "All services restarted"
else
  fail "Restart failed"
  printf '\n  Falling back to a clean stop and start.\n'
  "${SCRIPTS_DIR}/stop.sh" --yes || true
  exec "${SCRIPTS_DIR}/start.sh" ${EXTRA}
fi

step "Waiting for the API"
api_port="$(compose_host_port api 8000 8000)"
if wait_for_http "http://127.0.0.1:${api_port}/api/v1/runtime" 60 2 "api"; then
  ok "Platform is back up"
  printf '\n  Run ./scripts/status.sh for the full picture\n\n'
else
  fail "The API did not become ready after the restart"
  compose logs --tail 40 api 2>&1 | indent
  exit 1
fi
