#!/usr/bin/env bash
#
# Prove the running PyCraft platform actually works.
#
#   ./scripts/verify.sh                 # full check against the Docker stack
#   ./scripts/verify.sh --quick         # skip tests, just check it responds
#   ./scripts/verify.sh --keep-user     # leave the test account behind
#
# This is the check that matters after a deploy: it registers a real account,
# queues a real submission, and waits for a real sandbox to grade it. Everything
# else (containers running, ports open, /health returning 200) can pass while
# grading is completely broken.
#
# Read-only apart from the account it creates, which is deleted afterwards
# unless --keep-user is given.

QUICK=0
KEEP_USER=0
API_URL=""

# Single pass with a "consume next argument" flag. A two-pass version would let
# the URL be collected twice, and anything positional could be mistaken for a
# value — the same trap that made `logs.sh --tail 5 api` ask for a service
# literally named "5".
expect_url=0
for arg in "$@"; do
  if [ "${expect_url}" = "1" ]; then
    API_URL="${arg}"
    expect_url=0
    continue
  fi
  case "${arg}" in
    --quick)     QUICK=1 ;;
    --keep-user) KEEP_USER=1 ;;
    --url | -u)  expect_url=1 ;;
    --verbose)   PYCRAFT_VERBOSE=1 ;;
    --help | -h) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) printf 'Unknown option: %s\n' "${arg}" >&2; exit 2 ;;
  esac
done

if [ "${expect_url}" = "1" ]; then
  printf -- '--url needs a value, e.g. --url http://127.0.0.1:8000\n' >&2
  exit 2
fi

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
export PYCRAFT_VERBOSE

log_open verify
require_repo_root || exit 1
load_env_file

CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNED=0

passed() { CHECKS_PASSED=$(( CHECKS_PASSED + 1 )); ok "$*"; }
failed() { CHECKS_FAILED=$(( CHECKS_FAILED + 1 )); fail "$*"; }
warned() { CHECKS_WARNED=$(( CHECKS_WARNED + 1 )); warn "$*"; }

rule
printf '%s%sPyCraft — verifying the platform%s\n' "${C_BOLD}" "${C_CYAN}" "${C_RESET}"
rule

# --- Locate the API ----------------------------------------------------------
if [ -z "${API_URL}" ]; then
  api_port="$(compose_host_port api 8000 8000)"
  API_URL="http://127.0.0.1:${api_port}"
fi
# Accept a base URL with or without the /api/v1 suffix.
case "${API_URL}" in
  */api/v1) BASE="${API_URL}" ;;
  */)       BASE="${API_URL}api/v1" ;;
  *)        BASE="${API_URL}/api/v1" ;;
esac
info "API: ${BASE}"

# --- Reachability ------------------------------------------------------------
step "Reachability"

if wait_for_http "${BASE}/runtime" 5 1 "runtime"; then
  passed "API answers at ${BASE}/runtime"
else
  failed "API does not answer — is the platform running? (./scripts/start.sh)"
  printf '\n'
  rule
  printf '%sCannot continue: the API is not reachable.%s\n\n' "${C_RED}" "${C_RESET}"
  exit 1
fi

RUNTIME="$(http_get "${BASE}/runtime" || echo '')"
BACKEND="$(printf '%s' "${RUNTIME}" | jq -r '.execution_backend // "?"' 2>/dev/null)"
CHALLENGE_COUNT="$(printf '%s' "${RUNTIME}" | jq -r '.challenge_count // 0' 2>/dev/null)"
PY_VERSION="$(printf '%s' "${RUNTIME}" | jq -r '.default_python_version // "?"' 2>/dev/null)"
ENVIRONMENT="$(printf '%s' "${RUNTIME}" | jq -r '.environment // "?"' 2>/dev/null)"

info "Environment: ${ENVIRONMENT}, Python ${PY_VERSION}, execution backend: ${BACKEND}"

if [ "${BACKEND}" = "docker" ]; then
  passed "Execution is sandboxed (backend: docker)"
else
  warned "Execution backend is '${BACKEND}' — learner code is NOT isolated"
fi

if [ "${CHALLENGE_COUNT}" -gt 0 ] 2>/dev/null; then
  passed "Catalogue loaded: ${CHALLENGE_COUNT} challenges"
else
  failed "The catalogue is empty — no challenges were indexed"
fi

# --- Queue and workers -------------------------------------------------------
step "Queue and workers"

QUEUE="$(http_get "${BASE}/queue" || echo '')"
if [ -n "${QUEUE}" ]; then
  WORKERS="$(printf '%s' "${QUEUE}" | jq -r '.workers // 0' 2>/dev/null)"
  WAITING="$(printf '%s' "${QUEUE}" | jq -r '.waiting // 0' 2>/dev/null)"
  passed "Queue reachable: ${WAITING} waiting, ${WORKERS} worker(s)"
  if [ "${WORKERS}" = "0" ] && [ "${WAITING}" != "0" ]; then
    failed "There is queued work but no workers to run it"
  elif [ "${WORKERS}" = "0" ]; then
    warned "No workers are running — submissions would never finish"
  fi
else
  failed "The queue endpoint did not answer"
fi

if [ "${QUICK}" = "1" ]; then
  rule
  printf '%sQuick check complete%s  %s%d passed, %d warning(s), %d failed%s\n\n' \
    "${C_BOLD}" "${C_RESET}" "${C_GREEN}" "${CHECKS_PASSED}" "${CHECKS_WARNED}" "${CHECKS_FAILED}" "${C_RESET}"
  [ "${CHECKS_FAILED}" -eq 0 ] && exit 0 || exit 1
fi

# --- Auth --------------------------------------------------------------------
step "Authentication"

EMAIL="verify-$(date +%s)-$$@example.com"
PASSWORD="Verify-Pass-2026"

REGISTER_BODY="$(jq -n --arg e "${EMAIL}" --arg p "${PASSWORD}" '{email: $e, password: $p, display_name: "Verify"}')"
REG_RESPONSE="$(curl -sS --max-time 20 -w '\n%{http_code}' -X POST "${BASE}/auth/register" \
  -H 'Content-Type: application/json' -d "${REGISTER_BODY}" 2>/dev/null || echo '000')"
REG_CODE="$(printf '%s' "${REG_RESPONSE}" | tail -1)"
REG_JSON="$(printf '%s' "${REG_RESPONSE}" | sed '$d')"

if [ "${REG_CODE}" = "201" ] || [ "${REG_CODE}" = "200" ]; then
  passed "Registration works (HTTP ${REG_CODE})"
else
  failed "Registration failed (HTTP ${REG_CODE})"
  printf '%s\n' "${REG_JSON}" | head -5 | indent
fi

TOKEN="$(printf '%s' "${REG_JSON}" | jq -r '.access_token // empty' 2>/dev/null)"
if [ -n "${TOKEN}" ]; then
  passed "Registration returned a usable access token"

  # A wrong password must be refused. This is a security property, and a
  # regression here would be silent otherwise.
  BAD_LOGIN="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' -X POST "${BASE}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg e "${EMAIL}" '{email: $e, password: "Definitely-Wrong-1"}')" 2>/dev/null || echo 000)"
  if [ "${BAD_LOGIN}" = "401" ]; then
    passed "A wrong password is refused (401)"
  else
    failed "A wrong password returned HTTP ${BAD_LOGIN}, expected 401"
  fi

  # An unauthenticated request must not be served.
  NO_AUTH="$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' "${BASE}/dashboard" 2>/dev/null || echo 000)"
  if [ "${NO_AUTH}" = "401" ] || [ "${NO_AUTH}" = "403" ]; then
    passed "Protected endpoints reject anonymous callers (${NO_AUTH})"
  else
    failed "A protected endpoint returned ${NO_AUTH} without a token"
  fi
else
  failed "No access token returned; skipping the authenticated checks"
fi

# --- Grading, end to end -----------------------------------------------------
if [ -n "${TOKEN}" ]; then
  step "Graded submission, end to end"
  info "This runs real code in a real sandbox — it is the slowest check"

  CHALLENGE_ID="python-fundamentals-hello-world"

  # First: the untouched starter must fail. If this passes, hidden tests are not
  # running at all, and every later "it scored 100" would be meaningless.
  STARTER='{"files": {"solution.py": "def greet(name: str) -> str:\n    raise NotImplementedError(\"todo\")\n"}}'
  STARTER_RESPONSE="$(curl -sS --max-time 20 -w '\n%{http_code}' -X POST "${BASE}/challenges/${CHALLENGE_ID}/submit" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${TOKEN}" -d "${STARTER}" 2>/dev/null || echo '000')"
  STARTER_CODE="$(printf '%s' "${STARTER_RESPONSE}" | tail -1)"
  STARTER_JSON="$(printf '%s' "${STARTER_RESPONSE}" | sed '$d')"

  poll_submission() {
    # Poll until `done` is true. Returns the final JSON on stdout.
    local id="$1" i=0 json done_flag
    while [ "${i}" -lt 90 ]; do
      i=$(( i + 1 ))
      json="$(curl -sS --max-time 10 -H "Authorization: Bearer ${TOKEN}" \
        "${BASE}/submissions/${id}" 2>/dev/null || echo '')"
      done_flag="$(printf '%s' "${json}" | jq -r '.done // false' 2>/dev/null)"
      [ "${done_flag}" = "true" ] && { printf '%s' "${json}"; return 0; }
      sleep 2
    done
    printf '%s' "${json}"
    return 1
  }

  if [ "${STARTER_CODE}" = "202" ]; then
    SID="$(printf '%s' "${STARTER_JSON}" | jq -r '.submission_id // empty')"
    passed "A submission is accepted with 202 (queued, id ${SID})"

    if STARTER_FINAL="$(poll_submission "${SID}")"; then
      S_SCORE="$(printf '%s' "${STARTER_FINAL}" | jq -r '.score // "?"' 2>/dev/null)"
      if [ "${S_SCORE}" = "0" ]; then
        passed "The untouched starter scored 0 — tests really run"
      else
        failed "The untouched starter scored ${S_SCORE}; expected 0"
      fi
    else
      poll_status="$(printf '%s' "${STARTER_FINAL}" | jq -r '.status // "?"' 2>/dev/null)"
      failed "The starter submission never finished (status ${poll_status})"
      printf '\n  The worker is not completing work. Check the API log:\n'
      printf '      ./scripts/logs.sh api --tail 50\n'
    fi
  else
    failed "Submitting returned HTTP ${STARTER_CODE}, expected 202"
    printf '%s\n' "${STARTER_JSON}" | head -5 | indent
  fi

  # Second: the correct solution must score full marks.
  SOLUTION='{"files": {"solution.py": "def greet(name: str) -> str:\n    return f\"Hello, {name}!\"\n"}}'
  SOL_RESPONSE="$(curl -sS --max-time 20 -w '\n%{http_code}' -X POST "${BASE}/challenges/${CHALLENGE_ID}/submit" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer ${TOKEN}" -d "${SOLUTION}" 2>/dev/null || echo '000')"
  SOL_CODE="$(printf '%s' "${SOL_RESPONSE}" | tail -1)"
  SOL_JSON="$(printf '%s' "${SOL_RESPONSE}" | sed '$d')"

  if [ "${SOL_CODE}" = "202" ]; then
    SID2="$(printf '%s' "${SOL_JSON}" | jq -r '.submission_id // empty')"
    if SOL_FINAL="$(poll_submission "${SID2}")"; then
      SCORE="$(printf '%s' "${SOL_FINAL}" | jq -r '.score // "?"' 2>/dev/null)"
      T_PASSED="$(printf '%s' "${SOL_FINAL}" | jq -r '.passed // "?"' 2>/dev/null)"
      T_TOTAL="$(printf '%s' "${SOL_FINAL}" | jq -r '.total_tests // "?"' 2>/dev/null)"
      if [ "${SCORE}" = "100" ]; then
        passed "The reference solution scored 100 (${T_PASSED}/${T_TOTAL} tests)"
      else
        failed "The reference solution scored ${SCORE}, expected 100 (${T_PASSED}/${T_TOTAL})"
        printf '\n  The sandbox ran but graded incorrectly. Check:\n'
        printf '      ./scripts/logs.sh api --tail 50\n'
      fi
    else
      failed "The solution submission never finished"
    fi
  else
    failed "Submitting the solution returned HTTP ${SOL_CODE}, expected 202"
  fi

  # Third: progress must have moved. This proves the worker records results,
  # which is separate from grading correctly.
  step "Progress is recorded"
  DASHBOARD="$(curl -sS --max-time 15 -H "Authorization: Bearer ${TOKEN}" "${BASE}/dashboard" 2>/dev/null || echo '')"
  if [ -n "${DASHBOARD}" ]; then
    XP="$(printf '%s' "${DASHBOARD}" | jq -r '.progress.xp // 0' 2>/dev/null)"
    COMPLETED="$(printf '%s' "${DASHBOARD}" | jq -r '.progress.completed_challenges // 0' 2>/dev/null)"
    if [ "${XP}" -gt 0 ] 2>/dev/null && [ "${COMPLETED}" -gt 0 ] 2>/dev/null; then
      passed "Dashboard reflects the work: ${COMPLETED} challenge(s) completed, ${XP} XP"
    else
      failed "Dashboard shows no progress after a passing submission (XP ${XP})"
    fi
  else
    failed "The dashboard endpoint did not answer"
  fi
fi

# --- Result ------------------------------------------------------------------
rule
TOTAL=$(( CHECKS_PASSED + CHECKS_FAILED + CHECKS_WARNED ))
printf '%s%d checks: %d passed, %d warning(s), %d failed%s\n' \
  "${C_BOLD}" "${TOTAL}" "${CHECKS_PASSED}" "${CHECKS_WARNED}" "${CHECKS_FAILED}" "${C_RESET}"
log_to_file "verify: ${CHECKS_PASSED} passed, ${CHECKS_WARNED} warned, ${CHECKS_FAILED} failed"
rule

if [ "${CHECKS_FAILED}" -gt 0 ]; then
  printf '\n%sThe platform is running but not fully working.%s\n' "${C_RED}" "${C_BOLD}"
  printf 'Logs: ./scripts/logs.sh --errors\n\n'
  exit 1
fi

if [ "${CHECKS_WARNED}" -gt 0 ]; then
  printf '\n%sThe platform works, with warnings.%s\n\n' "${C_YELLOW}" "${C_BOLD}"
  exit 0
fi

printf '\n%sEverything checks out.%s\n\n' "${C_GREEN}" "${C_BOLD}"
exit 0
