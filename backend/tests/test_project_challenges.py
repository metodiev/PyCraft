"""Project challenges: multi-file structure, rubric and sandbox behaviour.

These tests run against the **real** content directory rather than a fixture,
because the point is to prove the shipped project challenge is well-formed and
actually discriminates. The sandbox assertions are Docker-marked.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.core.config import Settings
from app.services.challenges import ChallengeRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT = REPO_ROOT / "challenges"
PROJECT_ID = "backend-engineering-rest-api-service"


@pytest.fixture(scope="module")
def repository() -> ChallengeRepository:
    repo = ChallengeRepository(CONTENT)
    repo.load_all(strict=True)
    return repo


# --- content integrity ---------------------------------------------------
def test_all_shipped_content_loads(repository: ChallengeRepository) -> None:
    """CI guard: every challenge in the repo must be well-formed."""
    assert repository.errors == []
    assert len(repository.all()) >= 6


def test_project_is_detected(repository: ChallengeRepository) -> None:
    challenge = repository.get(PROJECT_ID)

    assert challenge.is_project is True
    assert challenge.kind == "project"


def test_project_ships_several_starter_files(repository: ChallengeRepository) -> None:
    challenge = repository.get(PROJECT_ID)

    assert set(challenge.files.starter_files) == {"router.py", "middleware.py", "service.py"}
    assert challenge.starter_file_count == 3
    # The entry file must be one the learner can actually edit.
    assert challenge.entry_file in challenge.files.starter_files


def test_project_has_a_rubric(repository: ChallengeRepository) -> None:
    """A project should explain how it is scored, not just be a big test suite."""
    challenge = repository.get(PROJECT_ID)

    assert len(challenge.files.rubric) >= 1
    total_weight = sum(int(entry["weight"]) for entry in challenge.files.rubric)
    assert total_weight == 100, f"rubric weights must total 100, got {total_weight}"
    for entry in challenge.files.rubric:
        assert entry["label"]
        assert entry["description"]


def test_project_has_both_test_suites(repository: ChallengeRepository) -> None:
    challenge = repository.get(PROJECT_ID)
    assert challenge.visible_test_count >= 1
    assert challenge.hidden_test_count >= 1


def test_single_file_challenges_are_not_projects(repository: ChallengeRepository) -> None:
    """A challenge with one starter file must not be flagged as a project."""
    for challenge in repository.all():
        if challenge.id == PROJECT_ID:
            continue
        assert challenge.is_project is False, challenge.id
        assert challenge.kind == "challenge", challenge.id


def test_project_starter_files_all_use_the_todo_marker(repository: ChallengeRepository) -> None:
    """An unsolved project must not contain a working implementation."""
    challenge = repository.get(PROJECT_ID)

    for name, source in challenge.files.starter_files.items():
        assert "NotImplementedError" in source, f"{name} has no NotImplementedError"
        assert "# TODO" in source or "TODO:" in source, f"{name} has no TODO marker"


def test_project_starter_does_not_import_outside_stdlib(repository: ChallengeRepository) -> None:
    challenge = repository.get(PROJECT_ID)
    forbidden = ("requests", "fastapi", "flask", "sqlalchemy", "django")

    for name, source in challenge.files.starter_files.items():
        for module in forbidden:
            assert f"import {module}" not in source, f"{name} imports {module}"


# --- sandbox behaviour (Docker) ------------------------------------------
pytestmark_docker = pytest.mark.docker


@pytest.mark.docker
async def test_project_starter_fails_in_the_sandbox(repository: ChallengeRepository) -> None:
    """The shipped starter must not already pass."""
    from app.execution.docker_backend import DockerExecutionBackend
    from app.execution.models import ExecutionLimits, ExecutionMode, ExecutionPayload

    challenge = repository.get(PROJECT_ID)
    backend = DockerExecutionBackend(Settings(environment="test"))
    await backend.start()
    try:
        report = await backend.execute(
            ExecutionPayload(
                files=dict(challenge.files.starter_files),
                tests=challenge.files.visible_tests,
                hidden_tests=challenge.files.hidden_tests,
                entry_file=challenge.entry_file,
                limits=ExecutionLimits(
                    time_limit_ms=challenge.time_limit_ms,
                    memory_limit_mb=challenge.memory_limit_mb,
                ),
                mode=ExecutionMode.SUBMIT,
                include_hidden=True,
            )
        )
    finally:
        await backend.stop()

    assert report.failed > 0
    assert report.status.value == "completed"


@pytest.mark.docker
async def test_project_correct_solution_passes_in_the_sandbox(
    repository: ChallengeRepository,
) -> None:
    """A correct multi-file solution must pass every test, visible and hidden."""
    from app.execution.docker_backend import DockerExecutionBackend
    from app.execution.models import ExecutionLimits, ExecutionMode, ExecutionPayload

    challenge = repository.get(PROJECT_ID)
    solution = dict(challenge.files.starter_files)
    solution.update(_REFERENCE_SOLUTION)

    backend = DockerExecutionBackend(Settings(environment="test"))
    await backend.start()
    try:
        report = await backend.execute(
            ExecutionPayload(
                files=solution,
                tests=challenge.files.visible_tests,
                hidden_tests=challenge.files.hidden_tests,
                entry_file=challenge.entry_file,
                limits=ExecutionLimits(
                    time_limit_ms=challenge.time_limit_ms,
                    memory_limit_mb=challenge.memory_limit_mb,
                ),
                mode=ExecutionMode.SUBMIT,
                include_hidden=True,
            )
        )
    finally:
        await backend.stop()

    assert report.succeeded, [t.message for t in report.tests if t.status.value != "passed"]
    assert report.total >= 20


_REFERENCE_SOLUTION = {
    "router.py": '''"""Path routing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Router:
    def __init__(self) -> None:
        self._routes: list[tuple[str, list[str], Callable[..., Any]]] = []

    def add_route(self, method: str, pattern: str, handler: Callable[..., Any]) -> None:
        stripped = pattern.strip("/")
        self._routes.append((method.upper(), stripped.split("/") if stripped else [], handler))

    def match(self, method: str, path: str):
        wanted = method.upper()
        stripped = path.strip("/")
        target = stripped.split("/") if stripped else []
        best, best_score = None, -1
        for route_method, segments, handler in self._routes:
            if route_method != wanted or len(segments) != len(target):
                continue
            params: dict[str, str] = {}
            literal = 0
            ok = True
            for seg, value in zip(segments, target):
                if seg.startswith("{") and seg.endswith("}"):
                    params[seg[1:-1]] = value
                elif seg == value:
                    literal += 1
                else:
                    ok = False
                    break
            if ok and literal > best_score:
                best, best_score = (handler, params), literal
        return best
''',
    "middleware.py": '''"""Middleware composition."""

from __future__ import annotations


class MiddlewarePipeline:
    def __init__(self, middlewares=None) -> None:
        self.middlewares = list(middlewares or [])

    def use(self, middleware):
        self.middlewares.append(middleware)
        return self

    def wrap(self, handler):
        wrapped = handler
        for middleware in reversed(self.middlewares):
            wrapped = middleware(wrapped)
        return wrapped
''',
    "service.py": '''"""Assembles the router and middleware into a callable service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from middleware import MiddlewarePipeline
from router import Router


@dataclass
class Response:
    status: int
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)


class RequestService:
    def __init__(self) -> None:
        self.router = Router()
        self.middlewares = MiddlewarePipeline()

    def route(self, method: str, pattern: str):
        def decorator(handler):
            self.router.add_route(method, pattern, handler)
            return handler

        return decorator

    def use(self, middleware):
        self.middlewares.use(middleware)
        return middleware

    def handle(self, method: str, path: str) -> Response:
        def dispatch(m: str, p: str):
            match = self.router.match(m, p)
            if match is None:
                return Response(404, {"error": "Not found"})
            handler, params = match
            try:
                return Response(200, handler(**params))
            except ValueError as exc:
                return Response(400, {"error": str(exc)})

        return self.middlewares.wrap(dispatch)(method, path)
''',
}
