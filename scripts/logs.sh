#!/usr/bin/env bash
#
# Read the PyCraft service logs.
#
#   ./scripts/logs.sh                 # all services, last 100 lines, then follow
#   ./scripts/logs.sh api             # just the API
#   ./scripts/logs.sh api web         # several services
#   ./scripts/logs.sh --no-follow api # print and exit (good for piping)
#   ./scripts/logs.sh --tail 500 api  # more history
#   ./scripts/logs.sh --errors        # only lines that look like errors
#   ./scripts/logs.sh --script        # this script's own run log
#
# Picking a service that does not exist lists the ones that do, rather than
# silently showing nothing.

FOLLOW=1
TAIL=100
ERRORS_ONLY=0
SHOW_SCRIPT=0
SERVICES=""

# Parsed in one pass with a "consume next argument" flag rather than two passes.
# An earlier version scanned for --tail twice, and the first pass had already
# treated the number as a service name — so `--tail 5 api` asked Docker for a
# service called "5". A single pass cannot disagree with itself.
expect_tail=0
for arg in "$@"; do
  if [ "${expect_tail}" = "1" ]; then
    case "${arg}" in
      '' | *[!0-9]*)
        printf -- '--tail needs a number, e.g. --tail 500 (got "%s")\n' "${arg}" >&2
        exit 2
        ;;
      *) TAIL="${arg}" ;;
    esac
    expect_tail=0
    continue
  fi

  case "${arg}" in
    --no-follow | -n) FOLLOW=0 ;;
    --follow | -f)    FOLLOW=1 ;;
    --tail | -t)      expect_tail=1 ;;
    --errors | -e)    ERRORS_ONLY=1 ;;
    --script | -s)    SHOW_SCRIPT=1 ;;
    --verbose)        PYCRAFT_VERBOSE=1 ;;
    --help | -h)      sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)               printf 'Unknown option: %s\n' "${arg}" >&2; exit 2 ;;
    *)                SERVICES="${SERVICES} ${arg}" ;;
  esac
done

if [ "${expect_tail}" = "1" ]; then
  printf -- '--tail needs a number, e.g. --tail 500\n' >&2
  exit 2
fi

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require_repo_root || exit 1
load_env_file

# --- The scripts' own log ----------------------------------------------------
if [ "${SHOW_SCRIPT}" = "1" ]; then
  latest="$(ls -t "${LOG_DIR}"/*.log 2>/dev/null | head -1 || true)"
  if [ -z "${latest}" ]; then
    printf 'No script logs yet in %s\n' "${LOG_DIR}" >&2
    exit 1
  fi
  printf '%s── %s%s\n' "${C_DIM}" "$(basename "${latest}")" "${C_RESET}"
  exec tail -n "${TAIL}" -f "${latest}"
fi

if ! docker info >/dev/null 2>&1; then
  printf 'The Docker daemon is not reachable.\n' >&2
  exit 1
fi

if ! resolve_compose; then
  printf 'Compose is unavailable — cannot read service logs.\n' >&2
  exit 1
fi

# --- Validate the requested services -----------------------------------------
if [ -n "${SERVICES}" ]; then
  for svc in ${SERVICES}; do
    # `compose config --services` is the authoritative list, so a service that
    # was renamed in docker-compose.yml is handled correctly.
    if ! compose config --services 2>/dev/null | grep -qx "${svc}"; then
      printf '%sUnknown service: %s%s\n\n' "${C_RED}" "${svc}" "${C_RESET}" >&2
      printf 'Available services:\n' >&2
      compose config --services 2>/dev/null | sed 's/^/    /' >&2
      printf '\nTip: --script shows the start/stop scripts\x27 own log.\n' >&2
      exit 2
    fi
  done
fi

# --- Build the tail command --------------------------------------------------
# `--tail` is passed to every service so the output starts with real context
# rather than the whole history of a long-running container.
TAIL_ARGS="--tail ${TAIL}"

if [ "${ERRORS_ONLY}" = "1" ]; then
  # Docker has no "errors only" filter, so pull a larger window and grep it.
  # The pattern spans the ways failures actually present across these services:
  # Python tracebacks, uvicorn errors, Postgres FATAL, nginx emergencies, and
  # PyCraft's own level-tagged log lines.
  info "Filtering for error-like lines (last ${TAIL} per service)"
  PATTERN='Traceback|ERROR|CRITICAL|Error:|error:|FATAL|Fatal|failed|FAILED|Exception|exception|refused|denied|unhealthy|panic'
  if [ -n "${SERVICES}" ]; then
    # shellcheck disable=SC2086
    compose logs ${TAIL_ARGS} ${SERVICES} 2>&1 | grep -E "${PATTERN}" | tail -200
  else
    compose logs ${TAIL_ARGS} 2>&1 | grep -E "${PATTERN}" | tail -200
  fi
  exit $?
fi

if [ "${FOLLOW}" = "1" ]; then
  # Ctrl-C stops the follow without disturbing the containers; say so, because
  # it is the obvious question when the screen stops scrolling.
  printf '%sfollowing logs — press Ctrl-C to stop watching (containers keep running)%s\n' "${C_DIM}" "${C_RESET}"
fi

log_to_file "\$ compose logs ${TAIL_ARGS} ${SERVICES} (follow=${FOLLOW})"

if [ "${FOLLOW}" = "1" ]; then
  # shellcheck disable=SC2086 # Word splitting is intended for the args.
  exec compose logs --follow ${TAIL_ARGS} ${SERVICES}
else
  # shellcheck disable=SC2086
  compose logs ${TAIL_ARGS} ${SERVICES}
fi
