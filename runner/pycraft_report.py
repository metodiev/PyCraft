"""pytest plugin that reports per-test outcomes as JSON.

Loaded by the runner via ``-p pycraft_report``. It intentionally avoids
third-party reporting packages so the execution image stays small and its
dependency surface stays auditable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_REPORT_ENV = "PYCRAFT_REPORT"


class PyCraftReporter:
    def __init__(self, config) -> None:  # noqa: ANN001 - pytest hook signature
        self.config = config
        self.results: list[dict] = []
        self.collection_error: str | None = None
        self._current: dict | None = None

    # --- collection / execution -----------------------------------------
    def pytest_collectreport(self, report) -> None:  # noqa: ANN001
        if report.failed:
            self.collection_error = _first_line(report.longrepr)

    def pytest_runtest_logstart(self, nodeid, location) -> None:  # noqa: ANN001
        self._current = {
            "name": _display_name(nodeid),
            "nodeid": nodeid,
            "status": "running",
            "duration_ms": 0,
            "message": "",
        }

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001
        if self._current is None:
            self._current = {
                "name": _display_name(report.nodeid),
                "nodeid": report.nodeid,
                "status": "running",
                "duration_ms": 0,
                "message": "",
            }

        if report.when == "call":
            self._current["duration_ms"] = int(report.duration * 1000)
            if report.passed:
                self._current["status"] = "passed"
            elif report.failed:
                self._current["status"] = "failed"
                self._current["message"] = _first_line(report.longrepr)
            elif report.skipped:
                self._current["status"] = "skipped"
                self._current["message"] = str(report.longrepr) if report.longrepr else ""
        elif report.when in {"setup", "teardown"} and report.failed:
            # Fixture/collection failures surface during setup, not call.
            self._current["status"] = "error"
            self._current["message"] = _first_line(report.longrepr)

        if report.when == "teardown":
            self._flush()

    def pytest_runtest_logfinish(self, nodeid, location) -> None:  # noqa: ANN001
        self._flush()

    def _flush(self) -> None:
        if self._current is None:
            return
        if self._current["status"] == "running":
            self._current["status"] = "error"
            self._current["message"] = "Test did not complete"
        self.results.append(self._current)
        self._current = None

    # --- session teardown ------------------------------------------------
    def pytest_sessionfinish(self, session, exitstatus) -> None:  # noqa: ANN001
        self._flush()
        passed = sum(1 for r in self.results if r["status"] == "passed")
        failed = sum(1 for r in self.results if r["status"] == "failed")
        errors = sum(1 for r in self.results if r["status"] == "error")
        skipped = sum(1 for r in self.results if r["status"] == "skipped")

        payload = {
            "tests": self.results,
            "summary": {
                "total": len(self.results),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped,
                "exit_status": int(exitstatus),
            },
            "collection_error": self.collection_error,
        }

        destination = Path(os.environ.get(_REPORT_ENV, "/tmp/pycraft-run/report.json"))
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            # Reporting must never mask the real test outcome.
            pass


def _display_name(nodeid: str) -> str:
    """Normalise a node id to ``<module>.py::<test>``.

    ``nodeid`` arrives either as ``tests/test_basic.py::test_greet`` or, if the
    ``tests`` directory is not importable as a package, as
    ``test_basic.py::test_greet``. Stripping the directory keeps the module
    filename — which is how the API distinguishes visible from hidden tests.
    """
    if "::" not in nodeid:
        return nodeid
    path, _, test_name = nodeid.partition("::")
    return f"{Path(path).name}::{test_name}"


def _first_line(repr_obj: object) -> str:
    """First meaningful line of a pytest failure representation."""
    if repr_obj is None:
        return ""
    lines = [line.strip() for line in str(repr_obj).splitlines() if line.strip()]
    for line in lines:
        if line.startswith("E ") or line.startswith("E\t"):
            return line[2:].strip()[:500]
    return lines[-1][:500] if lines else ""


def pytest_configure(config) -> None:  # noqa: ANN001
    reporter = PyCraftReporter(config)
    config.pluginmanager.register(reporter, "pycraft-reporter")
    config._pycraft_reporter = reporter  # noqa: SLF001 - pytest convention
