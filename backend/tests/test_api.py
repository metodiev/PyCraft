"""API tests covering the full user journey against the fake sandbox."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from httpx import AsyncClient
from tests.conftest import (
    FakeExecutionBackend,
    post_run,
    run_and_wait,
    submit_and_wait,
)

CHALLENGE = "python-fundamentals-hello-world"
SOLUTION = {"solution.py": "def greet(name):\n    return f'Hello, {name}!'\n"}
BROKEN = {"solution.py": "def greet(name):\n    return 'FAIL'\n"}


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_runtime_reports_backend_and_versions(client: AsyncClient) -> None:
    response = await client.get("/api/v1/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_backend"] == "fake"
    assert "3.12" in body["python_versions"]
    assert body["default_python_version"] == "3.12"
    assert body["challenge_count"] == 1


@pytest.mark.asyncio
async def test_lists_challenges(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/challenges")
    assert response.status_code == 200
    challenges = response.json()
    assert len(challenges) == 1
    assert challenges[0]["id"] == CHALLENGE
    assert challenges[0]["completed"] is False
    assert challenges[0]["visible_test_count"] == 1


@pytest.mark.asyncio
async def test_filters_challenges_by_track(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/challenges", params={"track": "python-fundamentals"})
    assert len(response.json()) == 1

    response = await anon_client.get("/api/v1/challenges", params={"track": "nonexistent"})
    assert response.json() == []


@pytest.mark.asyncio
async def test_challenge_detail_exposes_starter_but_not_hidden_tests(anon_client: AsyncClient) -> None:
    response = await anon_client.get(f"/api/v1/challenges/{CHALLENGE}")
    assert response.status_code == 200
    body = response.json()

    assert "def greet" in body["starter_code"]
    assert set(body["visible_tests"]) == {"test_visible.py"}
    assert body["entry_file"] == "solution.py"
    assert body["time_limit_ms"] == 5000
    # The hidden suite must never be serialised to the client.
    serialised = response.text
    assert "test_hidden" not in serialised
    assert "test_empty" not in serialised


@pytest.mark.asyncio
async def test_challenge_detail_reports_the_effective_memory_limit(
    anon_client: AsyncClient, settings: Settings
) -> None:
    """The workspace must not advertise a budget the sandbox will not grant.

    The fixture challenge declares 128 MB, which before the cap was exactly what
    it got. Now the ceiling clamps it, and the number the UI renders has to be
    the clamped one — otherwise a learner is told they have 128 MB while the
    container is killed at 100 MB.
    """
    response = await anon_client.get(f"/api/v1/challenges/{CHALLENGE}")
    assert response.status_code == 200

    assert response.json()["memory_limit_mb"] == settings.max_memory_limit_mb
    assert response.json()["memory_limit_mb"] <= settings.max_memory_limit_mb


@pytest.mark.asyncio
async def test_unknown_challenge_returns_404(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/api/v1/challenges/nope")).status_code == 404


@pytest.mark.asyncio
async def test_run_returns_output_without_grading(client: AsyncClient) -> None:
    body = await run_and_wait(client, CHALLENGE, SOLUTION)

    assert body["status"] == "completed"
    assert "hello from the fake sandbox" in body["stdout"]
    assert body["execution_time_ms"] == 120
    # Run reports no score: the field exists on every submission status, but is
    # only populated once a graded Submit has been processed.
    assert body["score"] is None


@pytest.mark.asyncio
async def test_run_excludes_hidden_tests(client: AsyncClient, fake_backend: FakeExecutionBackend) -> None:
    await run_and_wait(client, CHALLENGE, SOLUTION)

    payload = fake_backend.calls[-1]
    assert payload.include_hidden is False
    assert payload.to_wire()["hidden_tests"] == {}


@pytest.mark.asyncio
async def test_submit_includes_hidden_tests_and_scores(
    client: AsyncClient, fake_backend: FakeExecutionBackend
) -> None:
    body = await submit_and_wait(client, CHALLENGE, SOLUTION)

    assert fake_backend.calls[-1].include_hidden is True
    assert body["score"] == 100
    # 1 visible + 1 hidden test.
    assert body["total_tests"] == 2
    assert body["passed"] == 2
    assert body["failed"] == 0
    assert body["summary"].startswith("Excellent") or body["summary"].startswith("All")


@pytest.mark.asyncio
async def test_submit_marks_hidden_results_but_hides_their_messages(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, BROKEN)

    hidden = [r for r in body["results"] if r["hidden"]]
    visible = [r for r in body["results"] if not r["hidden"]]
    assert len(hidden) == 1
    assert len(visible) == 1
    assert all(r["message"] == "" for r in hidden)


@pytest.mark.asyncio
async def test_failing_submission_scores_below_pass(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, BROKEN)
    assert body["failed"] > 0
    assert body["score"] < 60


@pytest.mark.asyncio
async def test_submit_withholds_raw_output_to_protect_hidden_tests(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, SOLUTION)
    # A graded submission never returns the learner's raw output, because the
    # hidden suite runs beside their code and prints could leak it.
    assert body["stdout"] == ""
    assert body["stderr"] == ""


@pytest.mark.asyncio
async def test_progress_updates_after_successful_submit(client: AsyncClient) -> None:
    before = (await client.get("/api/v1/progress")).json()
    assert before["completed_challenges"] == 0
    assert before["xp"] == 0

    await submit_and_wait(client, CHALLENGE, SOLUTION)

    after = (await client.get("/api/v1/progress")).json()
    assert after["completed_challenges"] == 1
    assert after["completion_pct"] == 100
    # XP is the 50-point challenge plus any achievement bonuses earned along
    # the way, so assert the challenge portion is included rather than pinning
    # an exact total that changes whenever an achievement is added.
    assert after["xp"] >= 50
    assert after["level_id"] == "junior"


@pytest.mark.asyncio
async def test_xp_is_not_awarded_twice(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)
    after_first_pass = (await client.get("/api/v1/progress")).json()["xp"]

    await submit_and_wait(client, CHALLENGE, SOLUTION)

    progress = (await client.get("/api/v1/progress")).json()
    assert progress["completed_challenges"] == 1
    # Re-solving must not award the challenge's XP a second time. Achievements
    # are one-shot too, so the total is stable across repeats.
    assert progress["xp"] == after_first_pass


@pytest.mark.asyncio
async def test_failing_submit_does_not_complete_challenge(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, BROKEN)

    progress = (await client.get("/api/v1/progress")).json()
    assert progress["completed_challenges"] == 0
    assert progress["xp"] == 0

    challenges = (await client.get("/api/v1/challenges")).json()
    assert challenges[0]["completed"] is False


@pytest.mark.asyncio
async def test_challenge_list_reflects_completion(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    challenges = (await client.get("/api/v1/challenges")).json()
    assert challenges[0]["completed"] is True
    assert challenges[0]["best_score"] == 100


@pytest.mark.asyncio
async def test_dashboard_returns_full_payload(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    body = response.json()

    assert body["progress"]["completed_challenges"] == 1
    assert body["progress"]["xp"] >= 50
    assert body["progress"]["next_level_label"] == "Intermediate"
    assert len(body["recent_submissions"]) == 1
    assert body["recent_submissions"][0]["score"] == 100
    # Nothing left to recommend once the only challenge is complete.
    assert body["recommended_challenge"] is None


@pytest.mark.asyncio
async def test_dashboard_recommends_unstarted_challenge(client: AsyncClient) -> None:
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["recommended_challenge"]["id"] == CHALLENGE


@pytest.mark.asyncio
async def test_dashboard_continue_points_at_started_challenge(client: AsyncClient) -> None:
    await run_and_wait(client, CHALLENGE, SOLUTION)

    body = (await client.get("/api/v1/dashboard")).json()
    assert body["continue_challenge"]["id"] == CHALLENGE
    # Run alone must not complete the challenge.
    assert body["progress"]["completed_challenges"] == 0


@pytest.mark.asyncio
async def test_skill_bars_track_progress(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    skills = (await client.get("/api/v1/skills")).json()
    basics = next(s for s in skills if s["skill"] == "python.basics")
    assert basics["mastery"] == 100
    assert basics["challenges_completed"] == 1
    assert basics["challenges_total"] == 1


@pytest.mark.asyncio
async def test_roadmap_covers_every_stage(client: AsyncClient) -> None:
    roadmap = (await client.get("/api/v1/roadmap")).json()

    assert len(roadmap) == 13
    first = roadmap[0]
    assert first["id"] == "python-fundamentals"
    assert first["total_challenges"] == 1
    assert first["completed_challenges"] == 0
    # Stages without content yet are present but empty.
    assert roadmap[-1]["id"] == "principal-engineer"
    assert roadmap[-1]["total_challenges"] == 0
    assert roadmap[-1]["progress_pct"] == 0


@pytest.mark.asyncio
async def test_roadmap_marks_completed_stage(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    roadmap = (await client.get("/api/v1/roadmap")).json()
    assert roadmap[0]["progress_pct"] == 100


# --- request validation --------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "files",
    [
        {},
        {"solution.py": ""},
        {"solution.py": "x = 1", "other.txt": "nope"},
        {"../escape.py": "x = 1"},
        {"nested/solution.py": "x = 1"},
    ],
)
async def test_rejects_invalid_submissions(client: AsyncClient, files: dict) -> None:
    response = await post_run(client, CHALLENGE, files)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_oversized_file(client: AsyncClient) -> None:
    huge = {"solution.py": "x = 1\n" * 40_000}
    response = await post_run(client, CHALLENGE, huge)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_unknown_fields(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/challenges/{CHALLENGE}/run",
        json={"files": SOLUTION, "unexpected": True},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unknown_challenge_run_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/challenges/nope/run", json={"files": SOLUTION})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unknown_challenge_submit_returns_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/challenges/nope/submit", json={"files": SOLUTION})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_run_is_recorded_in_recent_submissions(client: AsyncClient) -> None:
    await run_and_wait(client, CHALLENGE, SOLUTION)

    body = (await client.get("/api/v1/dashboard")).json()
    recent = body["recent_submissions"]
    assert len(recent) == 1
    assert recent[0]["kind"] == "run"
    assert recent[0]["score"] is None


# --- multi-file projects -------------------------------------------------
@pytest.mark.asyncio
async def test_single_file_challenge_rejects_nested_paths(client: AsyncClient) -> None:
    """A nested filename is meaningless for a one-file challenge."""
    response = await client.post(
        f"/api/v1/challenges/{CHALLENGE}/run",
        json={"files": {"pkg/solution.py": "x = 1"}},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_single_file_challenge_rejects_hidden_paths(client: AsyncClient) -> None:
    response = await client.post(
        f"/api/v1/challenges/{CHALLENGE}/run",
        json={"files": {".hidden.py": "x = 1"}},
    )
    assert response.status_code == 422
