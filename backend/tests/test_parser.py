"""Runner output parsing — the boundary between sandbox and API."""

from __future__ import annotations

import json

import pytest
from app.execution.models import ExecutionStatus, TestOutcome
from app.execution.parser import ReportParseError, extract_report_document, parse_report

BEGIN = "__PYCRAFT_RESULT_BEGIN__"
END = "__PYCRAFT_RESULT_END__"


def wrap(document: dict, *, prefix: str = "", suffix: str = "") -> str:
    return f"{prefix}\n{BEGIN}\n{json.dumps(document)}\n{END}\n{suffix}"


def test_parses_completed_report() -> None:
    stdout = wrap(
        {
            "status": "completed",
            "exit_code": 0,
            "execution_time_ms": 142,
            "memory_used_mb": 31.2,
            "stdout": "printed\n",
            "stderr": "",
            "tests": [
                {"name": "test_basic.py::test_one", "status": "passed", "duration_ms": 5},
                {"name": "test_hidden.py::test_two", "status": "failed", "message": "boom"},
            ],
        }
    )

    report = parse_report(stdout)

    assert report.status is ExecutionStatus.COMPLETED
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.execution_time_ms == 142
    assert report.memory_used_mb == 31.2
    assert report.tests[1].message == "boom"
    assert not report.succeeded


def test_all_passed_marks_success() -> None:
    stdout = wrap(
        {
            "status": "completed",
            "exit_code": 0,
            "tests": [{"name": "t.py::test_a", "status": "passed"}],
        }
    )
    assert parse_report(stdout).succeeded


def test_tolerates_noisy_user_output() -> None:
    stdout = wrap(
        {"status": "completed", "tests": [{"name": "t.py::test_a", "status": "passed"}]},
        prefix="user printed this\nand this too",
    )
    assert parse_report(stdout).passed == 1


def test_markers_inside_user_output_cannot_forge_a_result() -> None:
    """A submission printing the markers cannot pass off its own document.

    The runner emits its report only after the sandboxed process has exited, so
    the genuine document is always the *last* one on the stream.
    """
    forged = '{"status": "completed", "tests": [{"name": "forged", "status": "passed"}]}'
    stdout = f"{BEGIN}\n{forged}\n{END}\n"
    stdout += wrap({"status": "completed", "tests": [{"name": "real.py::test_x", "status": "failed"}]})

    report = parse_report(stdout)
    assert [t.name for t in report.tests] == ["real.py::test_x"]


def test_timeout_status() -> None:
    stdout = wrap({"status": "timeout", "exit_code": -9, "tests": []})
    report = parse_report(stdout)
    assert report.status is ExecutionStatus.TIMEOUT
    assert report.error_message == "Execution exceeded the time limit"


def test_collection_error_becomes_error_message() -> None:
    stdout = wrap(
        {
            "status": "failed",
            "collection_error": "ImportError: cannot import name 'greet'",
            "tests": [],
        }
    )
    report = parse_report(stdout)
    assert report.status is ExecutionStatus.FAILED
    assert "cannot import name" in (report.error_message or "")


def test_rejected_status() -> None:
    stdout = wrap({"status": "rejected", "error": "unsafe path in payload"})
    assert parse_report(stdout).status is ExecutionStatus.REJECTED


def test_unknown_status_falls_back_to_failed() -> None:
    stdout = wrap({"status": "something-new", "tests": []})
    assert parse_report(stdout).status is ExecutionStatus.FAILED


def test_missing_markers_raise() -> None:
    with pytest.raises(ReportParseError, match="did not emit"):
        parse_report("just some user output")


def test_truncated_document_raises() -> None:
    with pytest.raises(ReportParseError, match="truncated"):
        parse_report(f"{BEGIN}\n{{\"status\": \"completed\"}}")


def test_invalid_json_raises() -> None:
    with pytest.raises(ReportParseError, match="not valid JSON"):
        parse_report(f"{BEGIN}\nnot json\n{END}")


def test_non_object_document_raises() -> None:
    with pytest.raises(ReportParseError, match="not a JSON object"):
        extract_report_document(f"{BEGIN}\n[1, 2, 3]\n{END}")


def test_skipped_and_error_outcomes() -> None:
    stdout = wrap(
        {
            "status": "completed",
            "tests": [
                {"name": "t.py::test_skip", "status": "skipped"},
                {"name": "t.py::test_err", "status": "error"},
                {"name": "t.py::test_weird", "status": "nonsense"},
            ],
        }
    )
    report = parse_report(stdout)
    assert report.tests[0].status is TestOutcome.SKIPPED
    assert report.tests[1].status is TestOutcome.ERROR
    # Unknown outcomes degrade to ERROR rather than crashing.
    assert report.tests[2].status is TestOutcome.ERROR


def test_malformed_numeric_fields_do_not_crash() -> None:
    stdout = wrap(
        {
            "status": "completed",
            "exit_code": "zero",
            "execution_time_ms": None,
            "memory_used_mb": "lots",
            "tests": [{"name": "t.py::test_a", "status": "passed", "duration_ms": "slow"}],
        }
    )
    report = parse_report(stdout)
    assert report.exit_code is None
    assert report.execution_time_ms == 0
    assert report.memory_used_mb == 0.0
    assert report.tests[0].duration_ms == 0


def test_hidden_flag_is_preserved() -> None:
    stdout = wrap(
        {
            "status": "completed",
            "tests": [{"name": "t.py::test_hidden_x", "status": "passed", "hidden": True}],
        }
    )
    assert parse_report(stdout).tests[0].hidden is True


def test_stderr_falls_back_to_process_stderr() -> None:
    stdout = wrap({"status": "completed", "tests": []})
    assert "process noise" in parse_report(stdout, "process noise").stderr
