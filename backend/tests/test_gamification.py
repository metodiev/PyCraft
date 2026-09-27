"""Gamification: achievements, streaks and leaderboards."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.models import User
from app.services.achievements import (
    ACHIEVEMENTS,
    ACHIEVEMENTS_BY_KEY,
    LearnerSnapshot,
    build_snapshot,
)
from app.services.streaks import (
    STREAK_GRACE_DAYS,
    effective_streak,
    register_activity,
    streak_is_alive,
)
from httpx import AsyncClient
from tests.conftest import submit_and_wait

CHALLENGE = "python-fundamentals-hello-world"
SOLUTION = {"solution.py": "def greet(name):\n    return f'Hello, {name}!'\n"}
BROKEN = {"solution.py": "def greet(name):\n    return 'FAIL'\n"}

ACHIEVEMENTS_URL = "/api/v1/achievements"
STREAK_URL = "/api/v1/streak"
LEADERBOARD_URL = "/api/v1/leaderboard"


def snapshot(**overrides: object) -> LearnerSnapshot:
    """A learner snapshot with everything at zero, ready to override."""
    base = LearnerSnapshot(
        user=User(email="s@example.com", display_name="S"),
        total_challenges=5,
        totals_by_track={"python-fundamentals": 3, "python-professional": 2},
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


# --- catalogue integrity -------------------------------------------------
def test_achievement_keys_are_unique() -> None:
    keys = [a.key for a in ACHIEVEMENTS]
    assert len(keys) == len(set(keys))


def test_achievement_registry_covers_every_definition() -> None:
    assert set(ACHIEVEMENTS_BY_KEY) == {a.key for a in ACHIEVEMENTS}


def test_achievements_have_required_metadata() -> None:
    for achievement in ACHIEVEMENTS:
        assert achievement.name, achievement.key
        assert achievement.description, achievement.key
        assert achievement.bonus_xp >= 0, achievement.key


def test_no_achievement_unlocks_on_a_blank_slate() -> None:
    """A brand-new learner must have earned nothing — and no free XP."""
    blank = snapshot()
    for achievement in ACHIEVEMENTS:
        assert not achievement.check(blank), f"{achievement.key} unlocked with zero progress"


def test_achievement_predicates_never_raise() -> None:
    """A predicate must survive odd snapshots rather than breaking a submission."""
    blank = snapshot(completed_by_track={}, totals_by_track={}, passed_by_difficulty={})
    for achievement in ACHIEVEMENTS:
        achievement.check(blank)  # must not raise


# --- individual predicates -----------------------------------------------
def test_first_steps_requires_one_solve() -> None:
    achievement = ACHIEVEMENTS_BY_KEY["first-steps"]
    assert achievement is not None
    assert not achievement.check(snapshot(completed_challenges=0))
    assert achievement.check(snapshot(completed_challenges=1))


def test_track_completion_requires_every_challenge_in_that_track() -> None:
    achievement = ACHIEVEMENTS_BY_KEY["foundations"]
    assert achievement is not None

    # Partial progress does not unlock.
    assert not achievement.check(snapshot(completed_challenges=2, completed_by_track={"python-fundamentals": 2}))
    # Full progress does.
    assert achievement.check(snapshot(completed_challenges=3, completed_by_track={"python-fundamentals": 3}))


def test_track_achievement_does_not_unlock_for_an_unshipped_track() -> None:
    """A track with no content must not count as complete."""
    achievement = ACHIEVEMENTS_BY_KEY["professional-python"]
    assert achievement is not None

    only_fundamentals = snapshot(
        completed_challenges=3,
        completed_by_track={"python-fundamentals": 3},
        totals_by_track={"python-fundamentals": 3},
    )
    assert not achievement.check(only_fundamentals)


def test_perfect_scores_are_tracked() -> None:
    achievement = ACHIEVEMENTS_BY_KEY["perfect-first-try"]
    assert achievement is not None
    assert not achievement.check(snapshot(perfect_scores=0))
    assert achievement.check(snapshot(perfect_scores=1))


def test_completion_percentage_guard() -> None:
    """A tiny catalogue must not make '25% done' trivially unlock."""
    achievement = ACHIEVEMENTS_BY_KEY["quarter-of-the-way"]
    assert achievement is not None
    # One challenge solved out of one is 100%, but the guard demands >= 4 total.
    assert not achievement.check(snapshot(total_challenges=1, completed_challenges=1))
    assert achievement.check(snapshot(total_challenges=4, completed_challenges=1))


def test_streak_achievements_use_longest_streak() -> None:
    """A lapsed streak must still have earned its achievement."""
    achievement = ACHIEVEMENTS_BY_KEY["streak-7"]
    assert achievement is not None
    assert not achievement.check(snapshot(longest_streak=6))
    assert achievement.check(snapshot(longest_streak=7, current_streak=0))


def test_explorer_requires_three_tracks() -> None:
    achievement = ACHIEVEMENTS_BY_KEY["explorer"]
    assert achievement is not None
    assert not achievement.check(snapshot(completed_by_track={"a": 1, "b": 1}))
    assert achievement.check(snapshot(completed_by_track={"a": 1, "b": 1, "c": 1}))


# --- streaks -------------------------------------------------------------
def test_first_activity_starts_a_streak() -> None:
    user = User(email="a@example.com", display_name="A")
    today = date(2026, 9, 27)

    assert register_activity(user, today) is True
    assert user.current_streak == 1
    assert user.longest_streak == 1
    assert user.last_active_date == today


def test_same_day_activity_does_not_advance_the_streak() -> None:
    user = User(email="a@example.com", display_name="A")
    today = date(2026, 9, 27)

    register_activity(user, today)
    assert register_activity(user, today) is False
    assert user.current_streak == 1


def test_consecutive_days_advance_the_streak() -> None:
    user = User(email="a@example.com", display_name="A")
    start = date(2026, 9, 20)

    for offset in range(5):
        register_activity(user, start + timedelta(days=offset))

    assert user.current_streak == 5
    assert user.longest_streak == 5


def test_streak_tolerates_a_one_day_gap() -> None:
    """A late-night session crossing midnight must not break the streak."""
    user = User(email="a@example.com", display_name="A")
    register_activity(user, date(2026, 9, 20))
    register_activity(user, date(2026, 9, 22))  # one missed day

    assert user.current_streak == 2


def test_long_gap_resets_the_streak_but_keeps_the_record() -> None:
    user = User(email="a@example.com", display_name="A")
    start = date(2026, 9, 1)
    for offset in range(6):
        register_activity(user, start + timedelta(days=offset))
    assert user.longest_streak == 6

    # A long absence.
    register_activity(user, start + timedelta(days=40))
    assert user.current_streak == 1
    assert user.longest_streak == 6


def test_streak_lapses_at_read_time() -> None:
    user = User(email="a@example.com", display_name="A")
    register_activity(user, date(2026, 9, 1))

    assert effective_streak(user, date(2026, 9, 2)) == 1
    assert effective_streak(user, date(2026, 9, 1 + STREAK_GRACE_DAYS)) == 1
    # Beyond the grace window the streak stops counting, without a submission.
    assert effective_streak(user, date(2026, 9, 10)) == 0


def test_streak_is_alive_reports_correctly() -> None:
    user = User(email="a@example.com", display_name="A")
    assert streak_is_alive(user, date(2026, 9, 1)) is False

    register_activity(user, date(2026, 9, 1))
    assert streak_is_alive(user, date(2026, 9, 2)) is True
    assert streak_is_alive(user, date(2026, 10, 1)) is False


# --- API -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_achievements_require_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(ACHIEVEMENTS_URL)).status_code == 401


@pytest.mark.asyncio
async def test_new_learner_has_nothing_unlocked(client: AsyncClient) -> None:
    response = await client.get(ACHIEVEMENTS_URL)
    assert response.status_code == 200
    body = response.json()

    assert body["earned"] == []
    assert body["earned_count"] == 0
    # Every achievement is listed as locked, so the UI can show the full set.
    assert body["total"] == len(ACHIEVEMENTS)
    assert len(body["locked"]) == len(ACHIEVEMENTS)


@pytest.mark.asyncio
async def test_solving_unlocks_first_steps(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    body = (await client.get(ACHIEVEMENTS_URL)).json()
    keys = {a["key"] for a in body["earned"]}
    assert "first-steps" in keys
    assert body["earned_count"] >= 1


@pytest.mark.asyncio
async def test_submit_reports_newly_unlocked_achievements(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, SOLUTION)

    assert "newly_unlocked" in body
    keys = {a["key"] for a in body["newly_unlocked"]}
    assert "first-steps" in keys
    # Each reported achievement carries its metadata for the celebration UI.
    first = next(a for a in body["newly_unlocked"] if a["key"] == "first-steps")
    assert first["name"] == "First Steps"
    assert first["tier"] == "bronze"
    assert first["bonus_xp"] > 0


@pytest.mark.asyncio
async def test_failing_submission_unlocks_nothing(client: AsyncClient) -> None:
    body = await submit_and_wait(client, CHALLENGE, BROKEN)

    assert body["newly_unlocked"] == []
    # And no XP, from challenges or achievements.
    progress = (await client.get("/api/v1/progress")).json()
    assert progress["xp"] == 0


@pytest.mark.asyncio
async def test_achievements_unlock_only_once(client: AsyncClient) -> None:
    first = await submit_and_wait(client, CHALLENGE, SOLUTION)
    second = await submit_and_wait(client, CHALLENGE, SOLUTION)

    assert len(first["newly_unlocked"]) >= 1
    # The second solve unlocks nothing new.
    assert second["newly_unlocked"] == []


@pytest.mark.asyncio
async def test_locked_achievements_expose_progress(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    body = (await client.get(ACHIEVEMENTS_URL)).json()
    five_solved = next((a for a in body["locked"] if a["key"] == "five-solved"), None)
    assert five_solved is not None
    assert five_solved["progress"] == {"current": 1, "target": 5}


@pytest.mark.asyncio
async def test_streak_endpoint_reports_activity(client: AsyncClient) -> None:
    before = (await client.get(STREAK_URL)).json()
    assert before["current"] == 0
    assert before["active_today"] is False

    await submit_and_wait(client, CHALLENGE, SOLUTION)

    after = (await client.get(STREAK_URL)).json()
    assert after["current"] == 1
    assert after["longest"] == 1
    assert after["active_today"] is True
    assert after["alive"] is True


@pytest.mark.asyncio
async def test_failed_submission_does_not_start_a_streak(client: AsyncClient) -> None:
    """Streaks reward solving, not merely attempting."""
    await submit_and_wait(client, CHALLENGE, BROKEN)

    streak = (await client.get(STREAK_URL)).json()
    assert streak["current"] == 0
    assert streak["active_today"] is False


@pytest.mark.asyncio
async def test_leaderboard_requires_no_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(LEADERBOARD_URL)).status_code == 200


@pytest.mark.asyncio
async def test_leaderboard_lists_solvers(client: AsyncClient, account) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    entries = (await client.get(LEADERBOARD_URL)).json()
    assert len(entries) >= 1
    entry = entries[0]
    assert entry["display_name"] == "Test Learner"
    assert entry["xp"] > 0
    assert entry["completed_challenges"] == 1
    assert entry["is_you"] is True


@pytest.mark.asyncio
async def test_leaderboard_omits_users_with_no_xp(anon_client: AsyncClient, client: AsyncClient) -> None:
    """Nobody should appear just for having registered."""
    entries = (await anon_client.get(LEADERBOARD_URL)).json()
    assert entries == []


@pytest.mark.asyncio
async def test_leaderboard_does_not_expose_emails(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    response = await client.get(LEADERBOARD_URL)
    assert "@" not in response.text


@pytest.mark.asyncio
async def test_my_rank_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(f"{LEADERBOARD_URL}/me")).status_code == 401


@pytest.mark.asyncio
async def test_my_rank_returns_position(client: AsyncClient) -> None:
    await submit_and_wait(client, CHALLENGE, SOLUTION)

    entry = (await client.get(f"{LEADERBOARD_URL}/me")).json()
    assert entry["rank"] == 1
    assert entry["is_you"] is True


@pytest.mark.asyncio
async def test_my_rank_null_when_no_xp(client: AsyncClient) -> None:
    assert (await client.get(f"{LEADERBOARD_URL}/me")).json() is None


@pytest.mark.asyncio
async def test_leaderboard_orders_by_descending_xp(
    anon_client: AsyncClient, second_client: AsyncClient
) -> None:
    """More XP ranks higher, regardless of who registered first."""
    from tests.conftest import register_account

    # Register the eventual leader SECOND, so a tie would rank them lower and
    # only a genuine XP difference can put them on top.
    leader = await register_account(anon_client, email="leader@example.com", display_name="Leader")
    trailer = await register_account(
        second_client, email="trailer@example.com", display_name="Trailer"
    )

    # "Trailer" solves nothing but attempts a failing submission.
    second_client.headers["Authorization"] = f"Bearer {trailer.access_token}"
    await second_client.post(
        f"/api/v1/challenges/{CHALLENGE}/submit",
        json={"files": {"solution.py": "def greet(name):\n    return 'FAIL'\n"}},
    )

    # "Leader" solves the challenge and gains XP.
    anon_client.headers["Authorization"] = f"Bearer {leader.access_token}"
    await submit_and_wait(anon_client, CHALLENGE, SOLUTION)

    entries = (await anon_client.get(LEADERBOARD_URL)).json()

    assert [entry["display_name"] for entry in entries] == ["Leader"]
    assert entries[0]["rank"] == 1
    assert entries[0]["xp"] > 0


# --- snapshot building ---------------------------------------------------
@pytest.mark.asyncio
async def test_snapshot_counts_completed_challenges(client: AsyncClient, account) -> None:
    import uuid as _uuid

    import app.db.session as db_session

    await submit_and_wait(client, CHALLENGE, SOLUTION)

    async with db_session.get_session_factory()() as session:
        # `account.user_id` is a string from JSON; the column is a UUID type.
        user = await session.get(User, _uuid.UUID(account.user_id))
        assert user is not None
        index = {
            "python-fundamentals-hello-world": type(
                "C", (), {"track": "python-fundamentals", "difficulty": "beginner"}
            )()
        }
        snap = await build_snapshot(session, user, challenge_index=index)

    assert snap.completed_challenges == 1
    assert snap.total_challenges == 1
    assert snap.perfect_scores == 1
    assert snap.passed_by_difficulty["beginner"] == 1
    assert snap.completion_pct == 100
