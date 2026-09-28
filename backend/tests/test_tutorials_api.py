"""Tutorial API: catalogue, detail and the per-user read marker."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from app.core.config import Settings
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from tests.conftest import FakeExecutionBackend, register_account, write_tutorial

TUTORIAL = "python-fundamentals-test-tutorial"
BASE = "/api/v1/tutorials"


async def test_catalogue_is_readable_signed_out(anon_client: AsyncClient) -> None:
    response = await anon_client.get(BASE)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["read_count"] == 0
    assert len(body["tracks"]) == 1

    track = body["tracks"][0]
    assert track["track"] == "python-fundamentals"
    # The label mirrors the roadmap's wording rather than a naive title-case.
    assert track["label"] == "Python Fundamentals"
    assert track["total"] == 1
    assert track["read_count"] == 0
    assert track["tutorials"][0]["id"] == TUTORIAL
    assert track["tutorials"][0]["read"] is False


async def test_detail_returns_the_article_body(anon_client: AsyncClient) -> None:
    response = await anon_client.get(f"{BASE}/{TUTORIAL}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == TUTORIAL
    assert "Read this" in body["content"]
    assert body["reading_minutes"] == 5


async def test_detail_carries_no_scoring_fields(anon_client: AsyncClient) -> None:
    """Reading is not graded, so no XP or points may appear."""
    body = (await anon_client.get(f"{BASE}/{TUTORIAL}")).json()

    assert "points" not in body
    assert "xp" not in body
    assert "completed" not in body


async def test_unknown_tutorial_returns_404(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(f"{BASE}/python-fundamentals-nope")).status_code == 404


async def test_marking_read_requires_authentication(anon_client: AsyncClient) -> None:
    response = await anon_client.post(f"{BASE}/{TUTORIAL}/read")

    assert response.status_code == 401


async def test_mark_read_then_clear(client: AsyncClient) -> None:
    marked = await client.post(f"{BASE}/{TUTORIAL}/read")
    assert marked.status_code == 200
    assert marked.json() == {"tutorial_id": TUTORIAL, "read": True}

    catalogue = (await client.get(BASE)).json()
    assert catalogue["read_count"] == 1
    assert catalogue["tracks"][0]["read_count"] == 1
    assert catalogue["tracks"][0]["tutorials"][0]["read"] is True

    cleared = await client.delete(f"{BASE}/{TUTORIAL}/read")
    assert cleared.status_code == 200
    assert cleared.json() == {"tutorial_id": TUTORIAL, "read": False}

    catalogue = (await client.get(BASE)).json()
    assert catalogue["read_count"] == 0
    assert catalogue["tracks"][0]["tutorials"][0]["read"] is False


async def test_marking_read_twice_is_idempotent(client: AsyncClient) -> None:
    await client.post(f"{BASE}/{TUTORIAL}/read")
    first = (await client.get(BASE)).json()
    await client.post(f"{BASE}/{TUTORIAL}/read")
    second = (await client.get(BASE)).json()

    assert first["read_count"] == second["read_count"] == 1


async def test_clearing_an_unread_tutorial_is_not_an_error(client: AsyncClient) -> None:
    response = await client.delete(f"{BASE}/{TUTORIAL}/read")

    assert response.status_code == 200
    assert response.json()["read"] is False


async def test_read_state_is_per_user(
    client: AsyncClient, second_client: AsyncClient
) -> None:
    """One learner's progress must never leak into another's catalogue."""
    await client.post(f"{BASE}/{TUTORIAL}/read")
    assert (await client.get(BASE)).json()["read_count"] == 1

    # ``second_client`` starts with no credentials, so this is the signed-out
    # view; it must not inherit the first learner's marker.
    assert (await second_client.get(BASE)).json()["read_count"] == 0

    other = await register_account(second_client, email="other@pycraft.example.com")
    second_client.headers["Authorization"] = f"Bearer {other.access_token}"

    assert (await second_client.get(BASE)).json()["read_count"] == 0
    # ...and the first learner still sees their own marker.
    assert (await client.get(BASE)).json()["read_count"] == 1


@pytest_asyncio.fixture
async def two_tutorial_client(
    tmp_path: Path, fake_backend: FakeExecutionBackend, tutorials_dir: Path
) -> AsyncIterator[AsyncClient]:
    """A client whose catalogue has a second tutorial in another track.

    The catalogue is read at startup, so content added after the shared app has
    started would never be picked up — this builds a dedicated application
    instead of mutating one that is already running.
    """
    write_tutorial(
        tutorials_dir,
        track="testing-quality",
        slug="other",
        tutorial_id="testing-quality-other",
        extra_metadata={"reading_minutes": 7},
    )
    settings = Settings(
        environment="test",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'tutorials.db'}",
        challenges_dir=tmp_path / "challenges",
        tutorials_dir=tutorials_dir,
        execution_backend="local",
        secret_key="test-secret-key-not-for-production-use",
        email_backend="console",
    )
    application = create_app(settings)
    application.state.execution_backend = fake_backend
    application.state.skip_workers = True

    async with application.router.lifespan_context(application), AsyncClient(
        transport=ASGITransport(app=application), base_url="http://testserver"
    ) as http:
        yield http


async def test_catalogue_reading_minutes_totals_every_track(
    two_tutorial_client: AsyncClient,
) -> None:
    body = (await two_tutorial_client.get(BASE)).json()

    assert body["total"] == 2
    assert body["reading_minutes"] == 12
    assert {track["track"] for track in body["tracks"]} == {
        "python-fundamentals",
        "testing-quality",
    }
    labels = {track["track"]: track["label"] for track in body["tracks"]}
    assert labels["python-fundamentals"] == "Python Fundamentals"
    assert labels["testing-quality"] == "Testing & Quality"


async def test_tracks_are_labelled_from_the_roadmap(anon_client: AsyncClient) -> None:
    """A label must never be empty, and must match the roadmap's wording."""
    body = (await anon_client.get(BASE)).json()

    labels = {track["track"]: track["label"] for track in body["tracks"]}
    assert labels["python-fundamentals"] == "Python Fundamentals"
    assert all(label for label in labels.values())
