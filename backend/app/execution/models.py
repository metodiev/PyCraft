"""Immutable value objects exchanged with the execution engine.

These types are the boundary between the API and whatever sandbox implementation
is configured (Docker today, Kubernetes or a remote runner later), so they
deliberately contain no Docker-specific concepts.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class ExecutionMode(enum.StrEnum):
    """Run shows visible tests only; Submit grades against the full suite."""

    RUN = "run"
    SUBMIT = "submit"


class ExecutionStatus(enum.StrEnum):
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    FAILED = "failed"
    REJECTED = "rejected"


class TestOutcome(enum.StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


# Tell pytest these are domain types, not test classes.
TestOutcome.__test__ = False  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    """Resource ceilings applied to a single execution."""

    time_limit_ms: int
    memory_limit_mb: int
    cpu_count: float = 1.0
    process_limit: int = 64
    output_limit_bytes: int = 64 * 1024
    tmpfs_size_mb: int = 64

    def clamped(self, *, max_time_ms: int, max_memory_mb: int) -> ExecutionLimits:
        """Clamp to the platform ceiling — a challenge may lower, never raise."""
        return ExecutionLimits(
            time_limit_ms=min(self.time_limit_ms, max_time_ms),
            memory_limit_mb=min(self.memory_limit_mb, max_memory_mb),
            cpu_count=self.cpu_count,
            process_limit=self.process_limit,
            output_limit_bytes=self.output_limit_bytes,
            tmpfs_size_mb=self.tmpfs_size_mb,
        )


@dataclass(frozen=True, slots=True)
class ExecutionPayload:
    """Everything the sandbox needs to evaluate one submission."""

    files: dict[str, str]
    tests: dict[str, str]
    hidden_tests: dict[str, str]
    entry_file: str
    limits: ExecutionLimits
    mode: ExecutionMode
    python_version: str = "3.12"
    # Only populated for Submit — Run must never leak hidden test content.
    include_hidden: bool = False

    def to_wire(self) -> dict[str, Any]:
        """Serialise for the runner, omitting hidden tests when not graded."""
        return {
            "files": self.files,
            "tests": self.tests,
            "hidden_tests": self.hidden_tests if self.include_hidden else {},
            "entry_file": self.entry_file,
            "timeout_ms": self.limits.time_limit_ms,
            "mode": str(self.mode),
            "python_version": self.python_version,
        }


@dataclass(slots=True)
class TestResult:
    __test__ = False  # pytest must not try to collect this domain type

    name: str
    status: TestOutcome
    duration_ms: int = 0
    message: str = ""
    hidden: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": str(self.status),
            "duration_ms": self.duration_ms,
            "message": self.message,
            "hidden": self.hidden,
        }


@dataclass(slots=True)
class ExecutionReport:
    """Normalised result of one sandbox execution."""

    status: ExecutionStatus
    tests: list[TestResult] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    execution_time_ms: int = 0
    memory_used_mb: float = 0.0
    error_message: str | None = None

    @property
    def total(self) -> int:
        return len(self.tests)

    @property
    def passed(self) -> int:
        return sum(1 for t in self.tests if t.status is TestOutcome.PASSED)

    @property
    def failed(self) -> int:
        return sum(1 for t in self.tests if t.status in {TestOutcome.FAILED, TestOutcome.ERROR})

    @property
    def succeeded(self) -> bool:
        return self.status is ExecutionStatus.COMPLETED and self.failed == 0 and self.total > 0


class ExecutionError(Exception):
    """Raised when the sandbox itself fails (not when user code fails)."""
