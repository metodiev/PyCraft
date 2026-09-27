"""Authoring API: access control, validation and publishing."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from tests.conftest import submit_and_wait
from tests.test_authoring import HIDDEN, VALID_DESCRIPTION, VALID_STARTER, VISIBLE

TRACKS = "/api/v1/authoring/tracks"
VALIDATE = "/api/v1/authoring/validate"
PUBLISH = "/api/v1/authoring/publish"
ACCESS = "/api/v1/authoring/access"


def draft_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "slug": "sum-two-numbers",
        "track": "python-fundamentals",
        "title": "Sum Two Numbers",
        "summary": "Add two integers.",
        "difficulty": "beginner",
        "level": "junior",
        "points": 50,
        "description": VALID_DESCRIPTION,
        "starter_code": VALID_STARTER,
        "visible_tests": dict(VISIBLE),
        "hidden_tests": dict(HIDDEN),
        "skills": ["python.functions"],
    }
    body.update(overrides)
    return body


# --- access control ------------------------------------------------------
@pytest.mark.asyncio
async def test_authoring_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(TRACKS)).status_code == 401


@pytest.mark.asyncio
async def test_learner_cannot_author(client: AsyncClient) -> None:
    """A learner must not be able to add content."""
    assert (await client.get(TRACKS)).status_code == 403
    assert (await client.post(VALIDATE, json=draft_body())).status_code == 403
    assert (await client.post(PUBLISH, json=draft_body())).status_code == 403


@pytest.mark.asyncio
async def test_learner_access_endpoint_reports_capability(client: AsyncClient) -> None:
    body = (await client.get(ACCESS)).json()
    assert body["can_author"] is False
    assert body["role"] == "learner"


@pytest.mark.asyncio
async def test_author_access_endpoint_reports_capability(admin_client: AsyncClient) -> None:
    body = (await admin_client.get(ACCESS)).json()
    assert body["can_author"] is True


@pytest.mark.asyncio
async def test_author_can_list_tracks(admin_client: AsyncClient) -> None:
    response = await admin_client.get(TRACKS)
    assert response.status_code == 200

    tracks = response.json()
    ids = {track["id"] for track in tracks}
    assert "python-fundamentals" in ids
    assert "distributed-systems" in ids
    # Every track must be a real roadmap stage.
    from app.services.roadmap import ROADMAP

    assert ids <= {stage.id for stage in ROADMAP}


# --- validation ----------------------------------------------------------
@pytest.mark.asyncio
async def test_valid_draft_reports_valid(admin_client: AsyncClient) -> None:
    response = await admin_client.post(VALIDATE, json=draft_body())
    assert response.status_code == 200

    body = response.json()
    assert body["valid"] is True
    assert body["error_count"] == 0


@pytest.mark.asyncio
async def test_validation_reports_every_problem_at_once(admin_client: AsyncClient) -> None:
    """All issues should surface together, not one per round trip."""
    response = await admin_client.post(
        VALIDATE,
        json=draft_body(slug="Bad Slug", title="", summary="", visible_tests={}, hidden_tests={}),
    )
    body = response.json()

    assert body["valid"] is False
    fields = {issue["field"] for issue in body["issues"]}
    assert {"slug", "title", "summary", "visible_tests", "hidden_tests"} <= fields
    assert body["error_count"] >= 5


@pytest.mark.asyncio
async def test_validation_flags_sandbox_incompatible_imports(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        VALIDATE,
        json=draft_body(
            visible_tests={"test_x.py": "import requests\n\n\ndef test_x():\n    assert True\n"}
        ),
    )
    body = response.json()
    assert body["valid"] is False
    assert any("sandbox" in issue["message"] for issue in body["issues"])


@pytest.mark.asyncio
async def test_validation_warnings_do_not_block(admin_client: AsyncClient) -> None:
    response = await admin_client.post(VALIDATE, json=draft_body(skills=[]))
    body = response.json()

    assert body["valid"] is True
    assert body["warning_count"] >= 1
    assert body["error_count"] == 0


@pytest.mark.asyncio
async def test_validation_rejects_unknown_fields(admin_client: AsyncClient) -> None:
    response = await admin_client.post(VALIDATE, json=draft_body(is_published=True))
    assert response.status_code == 422


# --- publishing ----------------------------------------------------------
@pytest.mark.asyncio
async def test_publish_creates_a_retrievable_challenge(admin_client: AsyncClient) -> None:
    response = await admin_client.post(PUBLISH, json=draft_body())
    assert response.status_code == 200
    assert response.json()["valid"] is True

    # The new challenge is immediately in the catalogue, no restart needed.
    detail = await admin_client.get("/api/v1/challenges/python-fundamentals-sum-two-numbers")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Sum Two Numbers"
    assert body["starter_code"] == VALID_STARTER
    # Hidden tests are never exposed, even to the author, through this endpoint.
    assert "test_hidden" not in response.text


@pytest.mark.asyncio
async def test_published_challenge_accepts_a_submission(admin_client: AsyncClient) -> None:
    """End to end: author it, then solve it."""
    await admin_client.post(PUBLISH, json=draft_body())

    body = await submit_and_wait(
        admin_client,
        "python-fundamentals-sum-two-numbers",
        {"solution.py": "def add(a, b):\n    return a + b\n"},
    )
    assert body["score"] == 100
    assert body["failed"] == 0


@pytest.mark.asyncio
async def test_publish_refuses_an_invalid_draft(admin_client: AsyncClient) -> None:
    """Nothing is written when validation fails."""
    response = await admin_client.post(PUBLISH, json=draft_body(title=""))
    assert response.status_code == 200
    body = response.json()

    assert body["valid"] is False
    assert body["error_count"] >= 1
    # The challenge must not exist.
    assert (
        await admin_client.get("/api/v1/challenges/python-fundamentals-sum-two-numbers")
    ).status_code == 404


@pytest.mark.asyncio
async def test_publish_then_edit_round_trip(admin_client: AsyncClient) -> None:
    await admin_client.post(PUBLISH, json=draft_body())

    loaded = await admin_client.get(
        "/api/v1/authoring/challenges/python-fundamentals/sum-two-numbers"
    )
    assert loaded.status_code == 200
    body = loaded.json()

    assert body["title"] == "Sum Two Numbers"
    # Hidden tests ARE returned here: this endpoint is for the author editing
    # their own work, and it is gated behind the author role.
    assert "test_hidden.py" in body["hidden_tests"]

    updated = await admin_client.post(PUBLISH, json=draft_body(title="Renamed Challenge"))
    assert updated.json()["valid"] is True

    reloaded = await admin_client.get(
        "/api/v1/authoring/challenges/python-fundamentals/sum-two-numbers"
    )
    assert reloaded.json()["title"] == "Renamed Challenge"


@pytest.mark.asyncio
async def test_load_unknown_challenge_for_editing_is_404(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/authoring/challenges/python-fundamentals/nope")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_catalogue_overview_lists_content(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/authoring/catalogue")
    assert response.status_code == 200

    body = response.json()
    assert body["total"] >= 1
    assert "python-fundamentals" in body["by_track"]
    assert body["load_errors"] == []
    # Tracks with no content yet are reported so an author can see gaps.
    assert "distributed-systems" in body["empty_tracks"]


@pytest.mark.asyncio
async def test_catalogue_overview_is_author_only(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/authoring/catalogue")).status_code == 403
