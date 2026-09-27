"""In-process execution backend for development.

.. warning::
   This backend runs user code directly on the host and provides **no sandbox**.
   It allows contributors to iterate when Docker is unavailable and refuses to
   start when ``environment`` is ``production``. Never enable it on a shared or
   internet-facing deployment; use the Docker backend instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.execution.base import ExecutionBackend
from app.execution.models import (
    ExecutionError,
    ExecutionPayload,
    ExecutionReport,
    ExecutionStatus,
)
from app.execution.parser import ReportParseError, parse_report

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class LocalExecutionBackend(ExecutionBackend):
    """Runs the runner entrypoint on the host. Development only."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._semaphore = asyncio.Semaphore(max(1, settings.execution_concurrency // 2))

    async def start(self) -> None:
        if self._settings.environment == "production":
            raise ExecutionError(
                "The 'local' execution backend is disabled in production because it "
                "provides no isolation. Configure a Docker host instead."
            )
        if not (REPO_ROOT / "runner" / "entrypoint.py").exists():
            raise ExecutionError(f"Runner entrypoint missing under {REPO_ROOT / 'runner'}")
        logger.warning(
            "LOCAL execution backend active — user code runs unsandboxed on this host. "
            "Development use only."
        )

    async def stop(self) -> None:
        return None

    @property
    def name(self) -> str:
        return "local"

    async def execute(self, payload: ExecutionPayload) -> ExecutionReport:
        if not payload.files:
            raise ExecutionError("Submission contains no files")

        limits = payload.limits.clamped(
            max_time_ms=self._settings.max_time_limit_ms,
            max_memory_mb=self._settings.max_memory_limit_mb,
        )
        async with self._semaphore:
            return await self._execute(payload, limits)

    async def _execute(self, payload: ExecutionPayload, limits: object) -> ExecutionReport:
        scratch = Path(tempfile.mkdtemp(prefix="pycraft-local-"))
        try:
            # Reuse the containerised runner verbatim: the same entrypoint, the
            # same payload contract, the same report format.
            document = json.dumps(payload.to_wire()).encode("utf-8")
            payload_file = scratch / "input.json"
            payload_file.write_bytes(document)

            env = {
                **os.environ,
                # Keep every local run in its own scratch tree so parallel
                # executions cannot read each other's files or reports.
                "PYCRAFT_SCRATCH": str(scratch),
                "PYCRAFT_RUNNER_PLUGIN": str(REPO_ROOT / "runner" / "pycraft_report.py"),
            }

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-B",
                str(REPO_ROOT / "runner" / "entrypoint.py"),
                cwd=scratch,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timeout = getattr(limits, "time_limit_ms", 5_000) / 1000 + 15
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(document), timeout=timeout
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                return ExecutionReport(
                    status=ExecutionStatus.TIMEOUT,
                    error_message="Execution exceeded the time limit",
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            try:
                return parse_report(stdout, stderr)
            except ReportParseError as exc:
                return ExecutionReport(
                    status=ExecutionStatus.FAILED,
                    error_message=f"Local runner produced no result: {exc}",
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=process.returncode,
                )
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
