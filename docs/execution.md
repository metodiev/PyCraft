# Python execution

How a submission becomes an isolated process and a structured result.

## Pipeline

```
POST /submit
   │
   ▼
ExecutionPayload              normalised, transport-agnostic value object
   │
   ▼
limits.clamped()              a challenge may lower, never raise, the ceiling
   │
   ▼
DockerExecutionBackend        semaphore-bounded execution
   │
   ├─ create staging volume
   ├─ helper container: write payload.json (put_archive)
   ├─ create sandbox container (hardened, volume mounted read-only)
   ├─ start, wait with timeout + grace
   └─ collect logs, remove container and volume
   │
   ▼
parse_report()                extract JSON between marker lines
   │
   ▼
ExecutionReport               normalised outcome
```

## The payload contract

The API and the runner share one JSON document — the only interface between
them:

```json
{
  "files":        { "solution.py": "<learner source>" },
  "tests":        { "test_visible.py": "<source>" },
  "hidden_tests": { "test_hidden.py": "<source>" },
  "entry_file":   "solution.py",
  "timeout_ms":   5000,
  "mode":         "run",
  "python_version": "3.12"
}
```

`hidden_tests` is empty unless `mode` is `submit` — Run physically cannot touch
the graded suite.

## Why the payload goes through a volume

The natural implementation, `docker cp` into the sandbox, **fails with
`--read-only`**: `put_archive` writes through the container's root filesystem
layer, so it is rejected regardless of tmpfs mounts. Verified behaviour:

```
read_only=False, /opt/payload (no tmpfs):  OK
read_only=True,  /tmp (tmpfs):             FAIL: 400 container rootfs is marked read-only
read_only=True,  named volume:             OK
```

So the payload is written into a named volume by a short-lived helper container,
and that volume is then mounted **read-only** into the sandbox. Two benefits
beyond working at all:

- The API host does not need to share a filesystem with the Docker daemon, which
  matters for Docker Desktop, Colima, and remote `DOCKER_HOST` setups.
- The mounted payload cannot be modified by the learner's code.

## The runner

[`runner/entrypoint.py`](../runner/entrypoint.py) runs inside the container:

1. Reads the payload from `/opt/payload/payload.json`.
2. Copies everything into `/tmp/pycraft-run` (the root filesystem is read-only,
   `/tmp` is a size-capped tmpfs).
3. Rejects any payload path that would escape the scratch directory.
4. Copies in the reporting plugin and a generated `pytest.ini` — including `-s`,
   because learners need their own `print()` output to debug.
5. Runs pytest **as a subprocess** with `-I -B` and a minimal environment, in a
   new process group, killed by process group on timeout so orphaned children
   cannot survive.
6. Prints one JSON document between marker lines:

```
__PYCRAFT_RESULT_BEGIN__
{"status":"completed","tests":[…],"summary":{…}}
__PYCRAFT_RESULT_END__
```

### Reporting plugin

[`runner/pycraft_report.py`](../runner/pycraft_report.py) is a pytest plugin that
records per-test outcomes, durations and first-line failure messages, then
writes them to `report.json`. It avoids third-party reporting packages to keep
the execution image's dependency surface auditable.

Test names are normalised to `<module>.py::<test>`. That module filename is how
the API distinguishes a hidden test from a visible one, so it is load-bearing.

## Interpreting the result

| `status` | Meaning | Score |
| --- | --- | --- |
| `completed` | pytest ran to completion | Computed normally |
| `timeout` | Wall-clock limit exceeded; process group killed | 0 |
| `failed` | Collection error, import error, or no tests collected | 0 |
| `rejected` | Payload refused by policy (e.g. path traversal) | 0 |

The backend adds a second timeout at the container level (`limit + 30s grace`) as
a safety net. The in-container limit is always tighter, so it fires first and
produces a real report rather than an unexplained kill.

## Resource limits

Per execution, from the challenge metadata, clamped by platform ceilings:

| Resource | Mechanism | Default | Ceiling |
| --- | --- | --- | --- |
| Wall clock | In-container subprocess timeout | challenge value | 10 s |
| Memory | `--memory` + `--memswap` (swap disabled) | 128 MB | 512 MB |
| CPU | `--cpus` | 1.0 | — |
| Processes | `--pids-limit` | 64 | — |
| Scratch space | tmpfs size | 64 MB | — |
| Output | Truncated server-side | 64 KB | — |

## Adding a Python version

Supporting 3.13 is deliberately small:

1. Add an image variant (parameterise `runner/Dockerfile`, or add a second
   Dockerfile) and build it as `pycraft-runner:3.13`.
2. Map the version to an image in the execution backend, keyed off
   `ExecutionPayload.python_version`.
3. Append the version to `SUPPORTED_PYTHON_VERSIONS` in
   [`app/api/runtime.py`](../backend/app/api/runtime.py) so the UI advertises it.
4. Set `"python_version": "3.13"` in the metadata of challenges that need it.

The wire format already carries `python_version`; nothing else changes.

## Adding an execution substrate

Implement `ExecutionBackend` ([`app/execution/base.py`](../backend/app/execution/base.py)) —
three methods (`start`, `stop`, `execute`) plus a `name`. Return an
`ExecutionReport`; the rest of the platform is indifferent to how it was
produced. This is the intended path to Kubernetes Jobs, Firecracker/gVisor
microVMs, or a dedicated runner fleet.
