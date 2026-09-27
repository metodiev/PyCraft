"""Execution engine: turns a submission into an isolated sandbox run."""

from app.execution.base import ExecutionBackend
from app.execution.docker_backend import DockerExecutionBackend
from app.execution.local_backend import LocalExecutionBackend

__all__ = ["DockerExecutionBackend", "ExecutionBackend", "LocalExecutionBackend"]
