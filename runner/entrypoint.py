"""PyCraft runner entrypoint.

Executes inside a locked-down container. Reads ``/opt/payload/payload.json``,
materialises the submission into a writable scratch directory, runs pytest and
prints a single JSON result document wrapped in marker lines so the host can
extract it from stdout regardless of what the user's code printed.

Contract (payload.json)::

    {
      "files":       {"solution.py": "<source>"},      # user-authored code
      "tests":       {"test_basic.py": "<source>"},    # visible tests
      "hidden_tests":{"test_hidden.py": "<source>"},   # graded-only tests
      "entry_file":  "solution.py",
      "timeout_ms":  5000,
      "mode":        "run" | "submit",
      "python_version": "3.12"
    }

Output is the JSON report produced by ``pycraft_report`` between the markers
below. This script must stay dependency-free (stdlib only).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

PAYLOAD_PATH = Path(os.environ.get("PYCRAFT_PAYLOAD", "/opt/payload")) / "payload.json"
PLUGIN_PATH = Path(
    os.environ.get("PYCRAFT_RUNNER_PLUGIN", "/opt/pycraft/pycraft_report.py")
)
SCRATCH = Path(os.environ.get("PYCRAFT_SCRATCH", "/tmp")) / "pycraft-run"
REPORT_PATH = SCRATCH / "report.json"

RESULT_BEGIN = "__PYCRAFT_RESULT_BEGIN__"
RESULT_END = "__PYCRAFT_RESULT_END__"
MAX_OUTPUT_CHARS = 60_000


class TimeoutError_(Exception):
    """Raised when the subprocess exceeds the challenge time limit."""


def _emit(payload: dict) -> None:
    """Write the result document to stdout using unambiguous markers."""
    sys.stdout.write(f"\n{RESULT_BEGIN}\n")
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write(f"\n{RESULT_END}\n")
    sys.stdout.flush()


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... [truncated {omitted} characters]\n"


def _materialise(payload: dict) -> None:
    """Copy the payload into the writable scratch directory."""
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH, ignore_errors=True)
    SCRATCH.mkdir(parents=True, exist_ok=True)

    for name, source in payload.get("files", {}).items():
        _safe_write(name, source)

    test_source_files = dict(payload.get("tests", {}))
    test_source_files |= dict(payload.get("hidden_tests", {}))
    for name, source in test_source_files.items():
        _safe_write(f"tests/{name}", source, allow_subdir=True)

    (SCRATCH / "tests" / "__init__.py").write_text("", encoding="utf-8")

    # The reporter plugin lives outside the scratch tree and the interpreter runs
    # in isolated mode, so publish it into the rootdir and register it from a
    # conftest. pytest inserts the conftest's directory on sys.path itself, which
    # is what makes the plain module name importable.
    plugin_source = PLUGIN_PATH.read_text(encoding="utf-8")
    (SCRATCH / PLUGIN_PATH.name).write_text(plugin_source, encoding="utf-8")
    (SCRATCH / "conftest.py").write_text(
        f'pytest_plugins = ["{PLUGIN_PATH.stem}"]\n', encoding="utf-8"
    )

    # pytest captures stdout by default, which would swallow anything the
    # learner prints. They need their own output to debug, so capture is off.
    # ``asyncio_default_fixture_loop_scope`` silences a pytest-asyncio warning
    # that would otherwise appear in the learner's stderr on every run.
    (SCRATCH / "pytest.ini").write_text(
        "[pytest]\n"
        "addopts = -p no:cacheprovider -p no:randomly --tb=short -q -s\n"
        "testpaths = tests\n"
        "asyncio_default_fixture_loop_scope = function\n"
        "filterwarnings =\n"
        "    ignore::DeprecationWarning:pytest_asyncio.*\n",
        encoding="utf-8",
    )


def _safe_write(relative: str, source: object, *, allow_subdir: bool = False) -> None:
    """Write a payload file, refusing traversal outside the scratch directory."""
    if not isinstance(source, str):
        raise ValueError(f"payload entry {relative!r} is not text")
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe path in payload: {relative!r}")
    if not allow_subdir and len(rel.parts) > 1:
        raise ValueError(f"unexpected nested path for user file: {relative!r}")

    target = (SCRATCH / rel).resolve()
    if not target.is_relative_to(SCRATCH.resolve()):
        raise ValueError(f"path escapes scratch directory: {relative!r}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")


def _run_pytest(timeout_ms: int) -> tuple[subprocess.CompletedProcess[str], int]:
    """Run pytest as a subprocess so user code cannot corrupt the runner."""
    env = {
        # Minimal, explicit environment: no host secrets, no proxies.
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(SCRATCH),
        "TMPDIR": str(SCRATCH),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONHASHSEED": "0",
        "PYCRAFT_REPORT": str(REPORT_PATH),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    }

    started = time.perf_counter()
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            "-I",
            "-B",
            "-X",
            "faulthandler",
            "-m",
            "pytest",
            str(SCRATCH / "tests"),
        ],
        cwd=SCRATCH,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        start_new_session=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_ms / 1000)
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        stdout, stderr = process.communicate()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return (
            subprocess.CompletedProcess(process.args, -9, stdout, stderr + "\n[PyCraft] time limit exceeded"),
            elapsed_ms,
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr), elapsed_ms


def _kill_tree(process: subprocess.Popen[str]) -> None:
    """Kill the whole process group — user code may have spawned children."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)


def _peak_memory_mb() -> float:
    """Peak RSS of all reaped children, in MB (Linux / macOS)."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        # ru_maxrss is KiB on Linux, bytes on macOS.
        divisor = 1024 if sys.platform != "darwin" else 1024 * 1024
        return round(usage.ru_maxrss / divisor, 2)
    except Exception:  # pragma: no cover - best-effort metric
        return 0.0


def _load_report() -> dict:
    if not REPORT_PATH.exists():
        return {"tests": [], "summary": {}}
    try:
        return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tests": [], "summary": {}}


def _read_payload() -> dict:
    """Read the payload.

    Primary channel is stdin: the API streams JSON in, which keeps the container
    root filesystem read-only and avoids depending on host directory sharing
    (fragile across Docker Desktop, Colima and remote daemons). A file mount is
    still accepted as a fallback so the image can be exercised by hand.
    """
    raw = ""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
        except OSError:
            raw = ""

    if not raw.strip():
        if not PAYLOAD_PATH.exists():
            raise ValueError("No payload received on stdin or mounted at /opt/payload")
        try:
            raw = PAYLOAD_PATH.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Unable to read payload: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Malformed payload: expected a JSON object")
    return payload


def main() -> int:
    try:
        payload = _read_payload()
    except ValueError as exc:
        _emit({"status": "rejected", "error": str(exc)})
        return 2

    timeout_ms = int(payload.get("timeout_ms", 5000))

    try:
        _materialise(payload)
    except ValueError as exc:
        _emit({"status": "rejected", "error": str(exc)})
        return 2

    process, elapsed_ms = _run_pytest(timeout_ms)
    report = _load_report()
    timed_out = process.returncode == -9

    summary = report.get("summary", {})
    tests = report.get("tests", [])

    status = "completed"
    if timed_out:
        status = "timeout"
    elif report.get("collection_error") or not tests:
        status = "failed"

    _emit(
        {
            "status": status,
            "exit_code": process.returncode,
            "execution_time_ms": elapsed_ms,
            "memory_used_mb": _peak_memory_mb(),
            "stdout": _truncate(process.stdout or ""),
            "stderr": _truncate(process.stderr or ""),
            "tests": tests,
            "summary": {
                "total": summary.get("total", len(tests)),
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "errors": summary.get("errors", 0),
            },
            "collection_error": report.get("collection_error"),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
