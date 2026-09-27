"""Backend-agnostic contract for the execution sandbox."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.execution.models import ExecutionError, ExecutionPayload, ExecutionReport


class ExecutionBackend(ABC):
    """Runs untrusted Python in isolation and returns a normalised report.

    Implementations own their own lifecycle (startup/shutdown) and must never
    let user code touch the API process directly.
    """

    @abstractmethod
    async def start(self) -> None:
        """Prepare the backend (build/verify images, warm connection pools)."""

    @abstractmethod
    async def stop(self) -> None:
        """Release resources held by the backend."""

    @abstractmethod
    async def execute(self, payload: ExecutionPayload) -> ExecutionReport:
        """Execute ``payload`` in isolation.

        Raises:
            ExecutionError: if the sandbox could not run the payload at all.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier shown in health/diagnostics output."""


__all__ = ["ExecutionBackend", "ExecutionError"]
