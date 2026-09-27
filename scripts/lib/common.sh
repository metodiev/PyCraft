#!/usr/bin/env bash
#
# Shared helpers for the PyCraft scripts.
#
# Sourced, not executed: `source "$(dirname "$0")/lib/common.sh"`.
#
# Everything here is written for the bash 3.2 that ships with macOS, so there
# are no associative arrays, no `${var,,}`, and no `mapfile`. Where a newer
# bash would be convenient the code says so instead of failing at run time.

# --- Strictness --------------------------------------------------------------
# `-u` (unset variable) and `-o pipefail` are safe here. `-e` is deliberately
# NOT set: these scripts check exit codes explicitly so they can explain a
# failure rather than dying at the first non-zero. Scripts that want `-e` turn
# it on themselves after sourcing.
set -u
set -o pipefail

# --- Paths -------------------------------------------------------------------
# Resolve through symlinks so a script invoked as ./scripts/start.sh and one
# invoked via a symlinked path agree on where the repository is.
_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$(cd "${_lib_dir}/.." && pwd)"
ROOT_DIR="$(cd "${SCRIPTS_DIR}/.." && pwd)"
LOG_DIR="${ROOT_DIR}/scripts/logs"
export ROOT_DIR SCRIPTS_DIR LOG_DIR

# --- Colours -----------------------------------------------------------------
# Disabled when stdout is not a terminal (piped to a file, captured by CI) and
# when NO_COLOR is set, so logs stay readable instead of full of escape codes.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'
  C_RED=$'\033[31m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'; C_MAGENTA=$'\033[35m'; C_CYAN=$'\033[36m'
else
  C_RESET=''; C_BOLD=''; C_DIM=''
  C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_MAGENTA=''; C_CYAN=''
fi

# --- Logging -----------------------------------------------------------------
# Every message is also appended to the run log, so a failed start can be
# diagnosed from the file afterwards without re-running with the terminal in
# view. `log_to_file` is set once the log file exists.
PYCRAFT_LOG_FILE=""
VERBOSE="${PYCRAFT_VERBOSE:-0}"

# Append to the log file if one has been opened. Never fails the script: a log
# write problem must not stop a platform start.
_log_raw() {
  [ -n "${PYCRAFT_LOG_FILE}" ] || return 0
  printf '%s\n' "$1" >>"${PYCRAFT_LOG_FILE}" 2>/dev/null || true
}

log_open() {
  mkdir -p "${LOG_DIR}" 2>/dev/null || true
  PYCRAFT_LOG_FILE="${LOG_DIR}/$1.log"
  : >"${PYCRAFT_LOG_FILE}" 2>/dev/null || PYCRAFT_LOG_FILE=""
  if [ -n "${PYCRAFT_LOG_FILE}" ]; then
    log_to_file "=== PyCraft ${1} — $(date)"
    log_to_file "host: $(uname -srm)"
    log_to_file "root: ${ROOT_DIR}"
  fi
  export PYCRAFT_LOG_FILE
}

# Record a line in the log file only (no terminal output). Used for the verbose
# detail that would drown the terminal but is exactly what is wanted later.
log_to_file() {
  _log_raw "[$(date -u +%H:%M:%S)] $1"
}

# Show a message in the terminal and record it.
_log() {
  local color="$1" tag="$2" msg="$3"
  printf '%s%s%s %s\n' "${color}" "${tag}" "${C_RESET}" "${msg}"
  _log_raw "[$(date -u +%H:%M:%S)] ${tag} ${msg}"
}

info()     { _log "${C_BLUE}"    "  ·" "$*"; }
ok()       { _log "${C_GREEN}"   "  ✓" "$*"; }
warn()     { _log "${C_YELLOW}"  "  ⚠" "$*"; }
fail()     { _log "${C_RED}"     "  ✗" "$*"; }
step()     { _log "${C_BOLD}${C_MAGENTA}" "▶" "$*"; }
skip()     { _log "${C_DIM}"     "  -" "$*"; }

# Detail that only appears with PYCRAFT_VERBOSE=1, but is always logged.
debug() {
  _log_raw "[$(date -u +%H:%M:%S)] DEBUG $*"
  if [ "${VERBOSE}" = "1" ]; then
    printf '%s    %s%s\n' "${C_DIM}" "$*" "${C_RESET}"
  fi
}

# A fatal, explained failure. The caller is expected to exit.
fatal() {
  fail "$*"
  _log_raw "FATAL $*"
  return 1
}

# --- Output helpers ----------------------------------------------------------
# Indent a command's output so it is visually attached to the step that ran it.
indent() {
  # sed rather than `while read` so a line without a trailing newline survives.
  sed 's/^/      /'
}

# A horizontal rule, for separating phases in the log.
rule() {
  printf '%s%s%s\n' "${C_DIM}" "──────────────────────────────────────────────────────────────" "${C_RESET}"
  _log_raw "--------------------------------------------------------------"
}

# --- Command running ---------------------------------------------------------
# Run a command, echoing it to the log, and return its exit status.
#
# Passwords must never reach the log, so callers that handle secrets use
# `run_quiet` or mask the value themselves; there is no way for this function to
# know a word is sensitive.
run() {
  log_to_file "\$ $*"
  "$@"
}

# Run a command with its output captured; print the output only on failure.
# Used for probes where the answer is a status, not text.
run_quiet() {
  local output status
  log_to_file "\$ $*"
  output="$("$@" 2>&1)"
  status=$?
  if [ "${status}" -ne 0 ]; then
    log_to_file "  (exit ${status})"
    [ -n "${output}" ] && log_to_file "${output}"
  fi
  if [ "${VERBOSE}" = "1" ] && [ -n "${output}" ]; then
    printf '%s%s%s\n' "${C_DIM}" "${output}" "${C_RESET}" | indent >&2
  fi
  LAST_OUTPUT="${output}"
  return "${status}"
}

# --- Platform detection ------------------------------------------------------
# The compose CLI is normally the `docker compose` plugin. Homebrew installs it
# as a separate `docker-compose` binary that the Docker CLI does not look for
# (it only searches ~/.docker/cli-plugins and a few system directories), so
# `docker compose` fails with "unknown command" on a perfectly working install.
# Probe both and remember which one works.
COMPOSE_CMD=""
resolve_compose() {
  if [ -n "${COMPOSE_CMD}" ]; then
    return 0
  fi

  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
    debug "compose: using the docker CLI plugin ('docker compose')"
    return 0
  fi

  if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
    debug "compose: plugin not discoverable by the docker CLI; using the standalone 'docker-compose' binary"
    return 0
  fi

  return 1
}

# Run the resolved compose command with the project directory pinned, so it
# works no matter which directory the caller is in.
compose() {
  resolve_compose || return 127
  # shellcheck disable=SC2086 # COMPOSE_CMD is intentionally word-split.
  ${COMPOSE_CMD} --project-directory "${ROOT_DIR}" -f "${ROOT_DIR}/docker-compose.yml" "$@"
}

# The path to bind-mount so the API can reach the Docker daemon.
#
# The subtlety: this is resolved by the daemon *inside its own VM*, not by the
# host. On colima and Docker Desktop the daemon runs in a VM where the socket is
# always at /var/run/docker.sock, even though no such file exists on the host.
# Passing the host-side path instead (e.g. ~/.colima/default/docker.sock) fails
# with "error while creating mount source path ... operation not supported",
# because the daemon cannot see the host filesystem at all.
#
# So the default is the daemon-side path, which is right for every install
# style, and an override exists for the unusual case of a remote daemon.
resolve_docker_socket() {
  printf '%s' "${PYCRAFT_DOCKER_SOCK:-/var/run/docker.sock}"
}

# Prove the daemon can actually bind-mount that path, before starting the stack.
#
# Without this the failure surfaces several steps later, from deep inside
# `docker compose up`, as a raw daemon error that gives no hint about the cause.
# A throwaway container with the same mount is a cheap and exact test.
check_docker_socket_mountable() {
  local sock="$1"
  run_quiet docker run --rm \
    -v "${sock}:/var/run/docker.sock" \
    --entrypoint /bin/true \
    "${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12}" 2>/dev/null
}

# --- Port checks -------------------------------------------------------------
# True if anything is LISTENing on the given TCP port.
#
# `lsof` reports client sockets too — a browser with a stale connection to a
# closed port keeps showing up — so only LISTEN is treated as a conflict. That
# distinction matters: Chrome holding a dead socket to :5173 is not a reason to
# refuse to start, and killing it would be actively wrong.
port_in_use() {
  lsof -nP -i "TCP:${1}" 2>/dev/null | grep -q LISTEN
}

# Print "pid <n> (<command>)" for whatever is listening on a port, for the log.
who_is_on_port() {
  local pid
  pid="$(lsof -nP -i "TCP:${1}" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  if [ -z "${pid}" ]; then
    printf 'unknown'
    return 0
  fi
  local cmd
  cmd="$(ps -o command= -p "${pid}" 2>/dev/null | head -1)"
  printf 'pid %s (%s)' "${pid}" "$(printf '%s' "${cmd}" | cut -c1-90)"
}

# Find the first free port at or after `start`, scanning at most 50.
# Used to keep a start working when a default port is already taken.
find_free_port() {
  local port="$1" limit=$(( $1 + 50 ))
  while [ "${port}" -lt "${limit}" ]; do
    if ! port_in_use "${port}"; then
      printf '%s' "${port}"
      return 0
    fi
    port=$(( port + 1 ))
  done
  return 1
}

# --- HTTP checks -------------------------------------------------------------
# Wait for a URL to answer. Returns 0 once something is listening and replying.
#
# Note there is no `timeout` command on macOS by default, and `curl` does not
# bound a connection attempt by itself, so `--max-time` is what stops this from
# hanging forever against a black-holed address.
wait_for_http() {
  local url="$1" attempts="${2:-60}" delay="${3:-2}" label="${4:-$1}"
  local i=1 code
  while [ "${i}" -le "${attempts}" ]; do
    if curl -fsS --max-time 5 -o /dev/null "${url}" 2>/dev/null; then
      debug "wait_for_http: ${label} answered after ${i} attempt(s)"
      return 0
    fi
    # A 4xx/5xx still proves something is listening; only connection failures
    # mean "not up yet". Distinguishing them stops a broken server from being
    # mistaken for a slow one.
    code="$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "${url}" 2>/dev/null || true)"
    if [ -n "${code}" ] && [ "${code}" != "000" ]; then
      debug "wait_for_http: ${label} responded ${code} (server is up)"
      return 0
    fi
    if [ "${i}" -eq "${attempts}" ]; then
      debug "wait_for_http: ${label} never answered after ${attempts} attempts"
      return 1
    fi
    sleep "${delay}"
    i=$(( i + 1 ))
  done
  return 1
}

# Fetch a URL and echo the body, failing on a connection error.
http_get() {
  curl -fsS --max-time 10 "$1" 2>/dev/null
}

# --- Confirmation ------------------------------------------------------------
# Ask before doing something destructive. Defaults to "no" so that a script run
# non-interactively (or with stdin closed) never destroys anything by accident.
confirm() {
  local prompt="$1" reply=""
  if [ ! -t 0 ]; then
    warn "${prompt} — no terminal to ask on, assuming no"
    return 1
  fi
  printf '%s%s%s [y/N] ' "${C_YELLOW}" "${prompt}" "${C_RESET}"
  read -r reply || reply=""
  case "${reply}" in
    [yY] | [yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

# --- Environment file --------------------------------------------------------
# Load .env if present so both the compose interpolation and the scripts agree
# on the port overrides.
load_env_file() {
  if [ -f "${ROOT_DIR}/.env" ]; then
    # shellcheck disable=SC1091 # Path is computed, not a literal.
    . "${ROOT_DIR}/.env"
    debug "loaded ${ROOT_DIR}/.env"
  fi
}

# --- Repository helpers ------------------------------------------------------
require_repo_root() {
  if [ ! -f "${ROOT_DIR}/docker-compose.yml" ]; then
    fatal "docker-compose.yml not found in ${ROOT_DIR} — is this the PyCraft repository?"
    return 1
  fi
  return 0
}

# The host port published for a container port. Reads compose's own resolved
# config rather than re-deriving it, so an override in .env cannot drift from
# what the script reports and probes.
compose_host_port() {
  local service="$1" container_port="$2" default="${3:-}"
  resolve_compose || { printf '%s' "${default}"; return 0; }
  local port
  port="$(compose config --format json 2>/dev/null \
    | jq -r --arg s "${service}" --argjson p "${container_port}" \
      '.services[$s].ports[]? | select(.target == $p) | .published' 2>/dev/null \
    | head -1)"
  if [ -n "${port}" ]; then
    printf '%s' "${port}"
  else
    printf '%s' "${default}"
  fi
}

# --- Docker port forwarders --------------------------------------------------
# True when the process listening on a port is Docker's own forwarder rather
# than a real service.
#
# Right after `docker compose down`, the forwarder for a published port can
# linger for a moment. Treating that as "somebody else owns this port" makes an
# immediate restart fail for no reason — which is exactly what a stop-then-start
# sequence does.
is_docker_forwarder() {
  local pid cmd
  pid="$(lsof -nP -i "TCP:${1}" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  [ -n "${pid}" ] || return 1
  cmd="$(ps -o command= -p "${pid}" 2>/dev/null | head -1)"
  case "${cmd}" in
    *docker* | *vpnkit* | *limactl* | *qemu*) return 0 ;;
    *) return 1 ;;
  esac
}

# Wait for a lingering Docker forwarder to release a port. Returns 1 if the
# port is held by a real process, in which case waiting would not help.
wait_for_forwarder_release() {
  local port="$1" attempts="${2:-10}" i=1
  while [ "${i}" -le "${attempts}" ]; do
    port_in_use "${port}" || return 0
    is_docker_forwarder "${port}" || return 1
    [ "${i}" -eq 1 ] && debug "port ${port} held by a Docker port-forwarder; waiting for release"
    sleep 1
    i=$(( i + 1 ))
  done
  return 1
}

# The group id that owns the Docker socket, as seen *inside* the daemon's VM.
#
# The API runs unprivileged and the socket is mode 660 owned by this group, so
# without joining it every connection is refused. The value differs per install
# (991 on colima, 0 on Docker Desktop) and cannot be read from the host
# filesystem, so it is queried from a throwaway container.
#
# Prints "0" when it cannot be determined, which is correct for Docker Desktop
# where the socket is group root.
resolve_docker_gid() {
  if [ -n "${PYCRAFT_DOCKER_GID:-}" ]; then
    printf '%s' "${PYCRAFT_DOCKER_GID}"
    return 0
  fi

  local gid
  gid="$(docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    --entrypoint sh "${PYCRAFT_RUNNER_IMAGE:-pycraft-runner:3.12}" \
    -c 'stat -c %g /var/run/docker.sock' 2>/dev/null | tr -dc '0-9')"

  if [ -z "${gid}" ]; then
    printf '0'
  else
    printf '%s' "${gid}"
  fi
}

# Prove the API's own unprivileged user can actually reach the daemon.
#
# Mounting the socket and connecting to it are different things: the socket is
# mode 660 owned by root and the daemon's group, so an unprivileged container
# can mount it happily and still be refused on connect. Checking the file mode
# would miss that — this opens a real connection as the API runs.
check_socket_connectable() {
  local sock="$1" gid="$2"
  run_quiet docker run --rm \
    -v "${sock}:/var/run/docker.sock" \
    --user 1000:1000 \
    --group-add "${gid}" \
    --entrypoint python \
    "${PYCRAFT_API_IMAGE:-pycraft-api}" \
    -c "import socket; socket.socket(socket.AF_UNIX).connect('/var/run/docker.sock')" 2>/dev/null
}
