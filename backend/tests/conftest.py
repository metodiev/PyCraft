"""Shared pytest fixtures.

Tests run against a temporary SQLite database and a temporary challenge
directory so they never touch developer state, and they default to a fake
execution backend so the suite is fast and Docker-independent. The real sandbox
is exercised by the ``docker``-marked tests.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from app.core.config import Settings
from app.execution.base import ExecutionBackend
from app.execution.models import (
    ExecutionPayload,
    ExecutionReport,
    ExecutionStatus,
    TestOutcome,
    TestResult,
)
from app.main import create_app
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

# A valid password under the configured policy.
TEST_PASSWORD = "PyCraft-Test-1234"


class FakeExecutionBackend(ExecutionBackend):
    """Deterministic stand-in for the sandbox.

    It honours the real semantics that tests care about — hidden tests are only
    present when ``include_hidden`` is set — without spawning containers.
    """

    def __init__(self) -> None:
        self.calls: list[ExecutionPayload] = []
        self.started = False
        self.report_factory = self._default_report

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    @property
    def name(self) -> str:
        return "fake"

    async def execute(self, payload: ExecutionPayload) -> ExecutionReport:
        self.calls.append(payload)
        return self.report_factory(payload)

    def _default_report(self, payload: ExecutionPayload) -> ExecutionReport:
        # A submission "succeeds" when it does not contain the failing marker.
        failing = any("FAIL" in source for source in payload.files.values())
        outcome = TestOutcome.FAILED if failing else TestOutcome.PASSED
        message = "AssertionError: assert 'FAIL' == 'Hello, !'" if failing else ""

        tests = [
            TestResult(
                name=f"{name[:-3]}::test_case_{index}",
                status=outcome,
                message=message,
                duration_ms=3,
            )
            for index, name in enumerate(sorted(payload.tests), start=1)
        ]
        if payload.include_hidden:
            tests.extend(
                TestResult(
                    name=f"{name[:-3]}::test_hidden_case_{index}",
                    status=outcome,
                    message=message,
                    duration_ms=2,
                )
                for index, name in enumerate(sorted(payload.hidden_tests), start=1)
            )
        return ExecutionReport(
            status=ExecutionStatus.COMPLETED,
            tests=tests,
            stdout="hello from the fake sandbox\n",
            stderr="",
            exit_code=0 if not failing else 1,
            execution_time_ms=120,
            memory_used_mb=21.5,
        )


def write_challenge(
    root: Path,
    *,
    track: str = "python-fundamentals",
    slug: str = "hello-world",
    challenge_id: str = "python-fundamentals-hello-world",
    difficulty: str = "beginner",
    points: int = 50,
    skills: list[str] | None = None,
    extra_metadata: dict | None = None,
) -> Path:
    """Materialise a minimal but valid challenge on disk."""
    path = root / track / slug
    (path / "starter").mkdir(parents=True)
    (path / "tests").mkdir(parents=True)

    metadata = {
        "id": challenge_id,
        "title": slug.replace("-", " ").title(),
        "summary": "A test challenge.",
        "difficulty": difficulty,
        "track": track,
        "module": "Test Module",
        "level": "junior",
        "python_version": "3.12",
        "time_limit_ms": 5000,
        "memory_limit_mb": 128,
        "points": points,
        "order_index": 1,
        "skills": skills if skills is not None else ["python.basics"],
        "entry_file": "solution.py",
        "tags": ["test"],
    }
    metadata.update(extra_metadata or {})
    (path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (path / "description.md").write_text("# Test challenge\n\nDo the thing.\n", encoding="utf-8")
    (path / "starter" / "solution.py").write_text(
        "def greet(name):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    (path / "tests" / "test_visible.py").write_text(
        "from solution import greet\n\n\ndef test_greet():\n    assert greet('W') == 'Hello, W!'\n",
        encoding="utf-8",
    )
    (path / "tests" / "test_hidden.py").write_text(
        "from solution import greet\n\n\ndef test_empty():\n    assert greet('') == 'Hello, !'\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def challenges_dir(tmp_path: Path) -> Path:
    root = tmp_path / "challenges"
    root.mkdir()
    write_challenge(root)
    return root


@pytest.fixture
def settings(tmp_path: Path, challenges_dir: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        challenges_dir=challenges_dir,
        execution_backend="local",
        execution_concurrency=2,
        # Fixed key so tokens survive across requests within a test.
        secret_key="test-secret-key-not-for-production-use",
        email_backend="console",
    )


@pytest.fixture
def fake_backend() -> FakeExecutionBackend:
    return FakeExecutionBackend()


@pytest.fixture
def app(settings: Settings, fake_backend: FakeExecutionBackend) -> FastAPI:
    application = create_app(settings)
    # Injected before startup; lifespan honours it over the configured backend.
    application.state.execution_backend = fake_backend
    # Tests drain the queue explicitly (see ``drain``) so they never race a
    # background worker and never depend on timing.
    application.state.skip_workers = True
    return application


async def drain(client: AsyncClient) -> int:
    """Process every runnable submission through the real worker path.

    Run and Submit return ``202`` immediately; this finishes the queued work so
    a test can assert on the result without racing a background worker.
    """
    from app.services.workers import WorkerPool

    application = client._app
    pool = WorkerPool(
        application.state.settings,
        application.state.execution_backend,
        application.state.challenges,
    )
    return await pool.run_until_idle()


async def run_and_wait(client: AsyncClient, challenge_id: str, files: dict[str, str]) -> dict:
    """POST a Run, drain the queue, and return the finished status body."""
    response = await client.post(f"/api/v1/challenges/{challenge_id}/run", json={"files": files})
    assert response.status_code == 202, response.text
    submission_id = response.json()["submission_id"]
    await drain(client)
    polled = await client.get(f"/api/v1/submissions/{submission_id}")
    assert polled.status_code == 200, polled.text
    return polled.json()


async def post_run(client: AsyncClient, challenge_id: str, files: dict) -> Response:
    """POST a Run and hand back the raw response.

    For cases that expect the request itself to be rejected, where there is
    nothing to drain and the status code is the assertion.
    """
    return await client.post(f"/api/v1/challenges/{challenge_id}/run", json={"files": files})


async def submit_and_wait(
    client: AsyncClient,
    challenge_id: str,
    files: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
) -> dict:
    """POST a Submit, drain the queue, and return the finished status body.

    ``headers`` is for tests that carry their own identity on a client shared
    with another account.
    """
    response = await client.post(
        f"/api/v1/challenges/{challenge_id}/submit", json={"files": files}, headers=headers
    )
    assert response.status_code == 202, response.text
    submission_id = response.json()["submission_id"]
    await drain(client)
    polled = await client.get(f"/api/v1/submissions/{submission_id}", headers=headers)
    assert polled.status_code == 200, polled.text
    return polled.json()


class Account:
    """A signed-in test account with an authenticated client bound to it."""

    def __init__(self, client: AsyncClient, payload: dict[str, Any]) -> None:
        self._client = client
        self.email: str = payload["user"]["email"]
        self.password: str = payload["_password"]
        self.access_token: str = payload["access_token"]
        self.refresh_token: str = payload["refresh_token"]
        self.user_id: str = payload["user"]["id"]

    @property
    async def me(self) -> dict[str, Any]:
        response = await self._client.get("/api/v1/auth/me")
        assert response.status_code == 200, response.text
        return response.json()

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}

    async def reauthenticate(self, http: AsyncClient) -> None:
        """Re-read tokens after an operation that rotated or revoked them."""
        response = await http.post(
            "/api/v1/auth/login", json={"email": self.email, "password": self.password}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.access_token = body["access_token"]
        self.refresh_token = body["refresh_token"]


async def register_account(
    http: AsyncClient,
    *,
    email: str,
    password: str = TEST_PASSWORD,
    display_name: str = "Test Learner",
) -> Account:
    """Register through the real endpoint and return an authenticated account."""
    response = await http.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    payload["_password"] = password
    return Account(http, payload)


@pytest_asyncio.fixture
async def running_app(app: FastAPI) -> AsyncIterator[FastAPI]:
    """The application with its lifespan started exactly once per test.

    Every HTTP client fixture depends on this, so multiple identities can be
    exercised against one initialised database and backend.
    """
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture
async def anon_client(running_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Unauthenticated client."""
    async with AsyncClient(
        transport=ASGITransport(app=running_app), base_url="http://testserver"
    ) as http:
        http._app = running_app
        yield http


@pytest_asyncio.fixture
async def second_client(running_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A second, independent client.

    Each ``AsyncClient`` owns its default headers, so two identities in one test
    need two clients — otherwise their Authorization headers overwrite each
    other.
    """
    async with AsyncClient(
        transport=ASGITransport(app=running_app), base_url="http://testserver"
    ) as http:
        http._app = running_app
        yield http


@pytest_asyncio.fixture
async def account(anon_client: AsyncClient) -> Account:
    """A default signed-in learner."""
    return await register_account(anon_client, email="learner@pycraft.example.com")


@pytest_asyncio.fixture
async def client(anon_client: AsyncClient, account: Account) -> AsyncClient:
    """A client authenticated as the default learner.

    Most tests exercise signed-in behaviour, so authentication is the default
    and `anon_client` is the explicit opt-out.
    """
    anon_client.headers["Authorization"] = f"Bearer {account.access_token}"
    return anon_client


@pytest_asyncio.fixture
async def admin_client(second_client: AsyncClient, settings: Settings) -> AsyncClient:
    """A client authenticated as an admin, independent of `client`."""
    email = "admin@pycraft.example.com"
    settings.admin_emails = [email]
    admin = await register_account(second_client, email=email, display_name="Admin")
    second_client.headers["Authorization"] = f"Bearer {admin.access_token}"
    return second_client


def auth_headers(account: Account) -> dict[str, str]:
    return {"Authorization": f"Bearer {account.access_token}"}
