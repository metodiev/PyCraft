# Security model

Untrusted Python is the core input to PyCraft. This document states what the
platform defends against, how, and what it explicitly does **not** claim.

## Threat model

Assume the learner is hostile and controls the full contents of every submitted
file. They may attempt to:

| Attack | Mitigation | Verified by |
| --- | --- | --- |
| Read or write host files | `--read-only` rootfs; scratch confined to a tmpfs | `test_root_filesystem_is_read_only` |
| Exfiltrate data or scan the network | `--network=none` | `test_network_is_unreachable` |
| Escalate to root | `--user 1000:1000`, `--cap-drop=ALL`, `--no-new-privileges` | `test_runs_as_unprivileged_user`, `test_privileged_operations_are_denied` |
| Exhaust CPU | `--cpus` plus an in-container wall-clock timeout | `test_timeout_is_enforced` |
| Exhaust memory | `--memory` / `--memswap` (swap disabled) | `test_memory_limit_is_enforced` |
| Fork bomb | `--pids-limit` | `test_fork_bomb_is_contained` |
| Read API secrets from the environment | Container gets an explicit minimal env | `test_host_environment_is_not_leaked` |
| Read other learners' submissions | Each run gets a fresh container, volume and scratch dir | `test_containers_are_cleaned_up` |
| Escape the scratch directory via the payload | Path traversal rejected before write | `test_payload_path_traversal_is_rejected` |

## Container hardening

Every execution container is created with:

```
--network=none                 no DNS, no egress, no SSRF pivot
--read-only                    immutable root filesystem
--cap-drop=ALL                 no capabilities (no ptrace, no raw sockets)
--security-opt=no-new-privileges  setuid binaries cannot elevate
--pids-limit=N                 fork-bomb containment
--memory / --memswap           hard memory ceiling, swap disabled
--cpus                         CPU quota
--user 1000:1000               never root
tmpfs /tmp (nosuid,nodev,size) isolated, size-capped scratch space
```

The runner image is `python:3.12-slim` plus pytest — no compilers, no network
tools, no package manager in the execution path.

## Limits are clamped, not trusted

A challenge's `metadata.json` can request limits, but the backend clamps them to
platform ceilings (`max_time_limit_ms`, `max_memory_limit_mb`). A malicious or
careless challenge file at worst _lowers_ its own budget; it can never raise the
host's.

The memory ceiling defaults to **100 MB** and exists to protect the host, not
merely the learner: a sandbox shares a host with the API container and the
PyCraft portal, so an unbounded submission is a denial-of-service against the
platform. The worst case is `worker_concurrency × max_memory_limit_mb`.

Execution is also bounded by a semaphore (`execution_concurrency`) so a
submission flood degrades throughput rather than exhausting the host.

## Hidden-test confidentiality

Hidden tests are materialised alongside the learner's code in the sandbox — they
have to be, in order to run. Two consequences follow, and both are handled
deliberately rather than by accident:

1. **Submit never returns raw stdout or stderr.** A learner can print anything
   they like, including the contents of the hidden test files, but that output
   is not echoed back on Submit. Only the structured pass/fail report is
   returned.
2. **Hidden failure messages are blanked.** The API returns the hidden test
   *names* (so learners can see the shape of the suite) but never their
   assertion messages, which would otherwise leak expected values.

3. **Run mode excludes hidden tests entirely.** `ExecutionPayload.to_wire()`
   omits them unless `include_hidden` is set, so experimentation can never touch
   the graded suite.

### Residual risk (accepted)

A determined learner can still reconnoiter *within* a single submit — for
example, by writing code that reads a hidden test file and branches on its
contents to pass. Since nothing is echoed back on Submit, exploiting this
requires blind guesswork across attempts, and the practical gain is a pass on
one challenge. The clean long-term fix is to run the hidden suite in a separate
container from the learner's code; that is deferred because it doubles container
startup on the critical path.

Do **not** treat hidden tests as a secret store. Never place credentials,
private URLs, or proprietary data in a `test_hidden*.py` file.

## Authentication

| Concern | Approach | Verified by |
| --- | --- | --- |
| Password storage | Argon2id via `pwdlib`, salted per hash | `test_password_hash_is_salted` |
| Account enumeration on login | Identical 401 for unknown email and wrong password, plus a dummy hash comparison so timing matches | `test_login_with_unknown_email_is_indistinguishable` |
| Account enumeration on reset | Always the same acknowledgement | `test_reset_request_does_not_reveal_account_existence` |
| Token theft via database dump | Refresh tokens stored only as SHA-256 digests | `test_opaque_token_hash_is_deterministic` |
| Refresh token replay | Rotation; a reused token revokes every session | `test_refresh_token_reuse_revokes_all_sessions` |
| Stale access tokens after logout | The JWT names a session that is checked on every request | `test_logout_revokes_the_session_immediately` |
| Token forgery | HS256 with a server-side key; a token signed with another key is rejected | `test_me_rejects_token_signed_with_another_key` |
| OAuth state forgery | Signed, 10-minute, single-purpose JWT | `test_state_rejects_tampered_redirect` |
| Open redirect via OAuth | `redirect_to` must be a same-site path; else falls back to `/` | `test_state_neutralises_open_redirect_attempts` |
| Account takeover via unverified email | Only verified provider emails are accepted for linking | `test_ignores_unverified_primary_email` |
| Privilege escalation via profile update | `role` and `xp` are not in the update schema | `test_profile_rejects_role_escalation` |
| Self-lockout | An admin cannot demote their own account | `test_admin_cannot_demote_self` |
| Cross-user session revocation | Session ids are scoped to the caller (`404` otherwise) | `test_cannot_revoke_another_users_session` |

Notes:

- **The signing key is mandatory in production.** With `PYCRAFT_SECRET_KEY`
  unset, a production instance refuses to start rather than signing with a key
  that changes on restart.
- **Access tokens are short-lived (15 min) but not individually revocable.**
  Revocation happens at the session level. Shortening the TTL shrinks the
  exposure window at the cost of more refreshes.
- **`state` is signed rather than stored.** That avoids a database round trip
  and gives tamper-evidence, at the cost of being replayable within its 10-minute
  window. GitHub's authorization codes are themselves single-use, which bounds
  the impact.

## Sandbox trust boundary

```
learner code  ──►  sandbox container  ──►  Docker daemon  ──►  API process
   untrusted          distrusted            trusted           trusted
```

The API is trusted infrastructure and never sees learner code. The Docker daemon
socket is mounted into the API container in `docker-compose.yml`, which is why
that compose file is for **local development only** — the socket grants effective
root on the host. Production must use a remote/additional daemon, a rootless
runtime, or a dedicated execution node.

## Reporting a vulnerability

Open a private security advisory on the repository rather than a public issue.
Include a reproducer payload if one exists.
