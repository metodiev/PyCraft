"""Parse the runner's stdout into a structured report.

The runner writes a JSON document between two marker lines so the result is
recoverable even when user code prints arbitrary text to stdout first.
"""

from __future__ import annotations

import json
from typing import Any

from app.execution.models import (
    ExecutionReport,
    ExecutionStatus,
    TestOutcome,
    TestResult,
)

RESULT_BEGIN = "__PYCRAFT_RESULT_BEGIN__"
RESULT_END = "__PYCRAFT_RESULT_END__"


class ReportParseError(ValueError):
    """Raised when the runner output does not contain a valid report."""


def extract_report_document(stdout: str) -> dict[str, Any]:
    """Pull the JSON document out of the runner's stdout.

    The **last** begin marker is used: the runner only ever emits one document,
    and it emits it after the sandboxed process has exited, so any markers a
    submission printed itself necessarily appear earlier and are ignored.
    """
    start = stdout.rfind(RESULT_BEGIN)
    if start == -1:
        raise ReportParseError("Runner did not emit a result document")

    body_start = start + len(RESULT_BEGIN)
    end = stdout.find(RESULT_END, body_start)
    if end == -1:
        raise ReportParseError("Runner result document was truncated")

    raw = stdout[body_start:end].strip()
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReportParseError(f"Runner result document was not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ReportParseError("Runner result document was not a JSON object")
    return document


def parse_report(stdout: str, stderr: str = "") -> ExecutionReport:
    """Convert runner stdout into an :class:`ExecutionReport`."""
    document = extract_report_document(stdout)

    raw_status = str(document.get("status", "failed"))
    status = {
        "completed": ExecutionStatus.COMPLETED,
        "timeout": ExecutionStatus.TIMEOUT,
        "failed": ExecutionStatus.FAILED,
        "rejected": ExecutionStatus.REJECTED,
    }.get(raw_status, ExecutionStatus.FAILED)

    tests = [_parse_test(item) for item in document.get("tests", []) if isinstance(item, dict)]

    return ExecutionReport(
        status=status,
        tests=tests,
        stdout=str(document.get("stdout", "")),
        stderr=str(document.get("stderr", "")) or stderr,
        exit_code=_as_int(document.get("exit_code")),
        execution_time_ms=_as_int(document.get("execution_time_ms")) or 0,
        memory_used_mb=_as_float(document.get("memory_used_mb")),
        error_message=_error_message(document),
    )


def _parse_test(item: dict[str, Any]) -> TestResult:
    raw = str(item.get("status", "error"))
    outcome = {
        "passed": TestOutcome.PASSED,
        "failed": TestOutcome.FAILED,
        "error": TestOutcome.ERROR,
        "skipped": TestOutcome.SKIPPED,
    }.get(raw, TestOutcome.ERROR)
    return TestResult(
        name=str(item.get("name", "unknown")),
        status=outcome,
        duration_ms=_as_int(item.get("duration_ms")) or 0,
        message=str(item.get("message", ""))[:2000],
        hidden=bool(item.get("hidden", False)),
    )


def _error_message(document: dict[str, Any]) -> str | None:
    if document.get("error"):
        return str(document["error"])
    if document.get("collection_error"):
        return f"Test collection failed: {document['collection_error']}"
    if document.get("status") == "timeout":
        return "Execution exceeded the time limit"
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
