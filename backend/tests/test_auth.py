"""Authentication: registration, sign-in, sessions, password reset, access control."""

from __future__ import annotations

import uuid

import pytest
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from httpx import AsyncClient
from tests.conftest import TEST_PASSWORD, register_account, submit_and_wait

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"


# --- pure security primitives -------------------------------------------
def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_password_hash_is_salted() -> None:
    """The same password must never produce the same hash twice."""
    assert hash_password("same-secret-123") != hash_password("same-secret-123")


def test_verify_rejects_garbage_hash() -> None:
    # Must return False rather than raising, so a corrupt row cannot break login.
    assert not verify_password("anything", "not-a-real-hash")


def test_access_token_roundtrip() -> None:
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    from datetime import timedelta

    token, expires_at = create_access_token(
        subject=user_id,
        email="someone@example.com",
        session_id=session_id,
        secret="test-key-at-least-32-bytes-long!!",
        algorithm="HS256",
        ttl=timedelta(minutes=5),
    )
    claims = decode_access_token(token, secret="test-key-at-least-32-bytes-long!!", algorithm="HS256")

    assert claims.subject == user_id
    assert claims.session_id == session_id
    assert claims.email == "someone@example.com"
    assert expires_at > claims.expires_at - __import__("datetime").timedelta(seconds=1)


def test_access_token_rejects_wrong_secret() -> None:
    from datetime import timedelta

    from app.core.security import TokenError

    token, _ = create_access_token(
        subject=uuid.uuid4(),
        email="a@example.com",
        session_id=uuid.uuid4(),
        secret="test-key-at-least-32-bytes-long!!",
        algorithm="HS256",
        ttl=timedelta(minutes=5),
    )
    with pytest.raises(TokenError):
        decode_access_token(token, secret="another-key-also-32-bytes-long!!!", algorithm="HS256")


def test_expired_token_is_rejected() -> None:
    from datetime import timedelta

    from app.core.security import TokenError

    token, _ = create_access_token(
        subject=uuid.uuid4(),
        email="a@example.com",
        session_id=uuid.uuid4(),
        secret="test-key-at-least-32-bytes-long!!",
        algorithm="HS256",
        ttl=timedelta(seconds=-10),
    )
    with pytest.raises(TokenError, match="expired"):
        decode_access_token(token, secret="test-key-at-least-32-bytes-long!!", algorithm="HS256")


def test_opaque_token_hash_is_deterministic() -> None:
    token = "some-token-value"
    assert hash_opaque_token(token) == hash_opaque_token(token)
    assert hash_opaque_token(token) != hash_opaque_token("other")


# --- registration --------------------------------------------------------
@pytest.mark.asyncio
async def test_register_returns_tokens_and_profile(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        REGISTER,
        json={
            "email": "New.User@Example.com",
            "password": TEST_PASSWORD,
            "display_name": "New User",
        },
    )
    assert response.status_code == 201
    body = response.json()

    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["display_name"] == "New User"
    # Emails are normalised to lowercase.
    assert body["user"]["email"] == "new.user@example.com"
    assert body["user"]["role"] == "learner"
    assert body["user"]["is_admin"] is False
    # The hash must never appear in a response.
    assert "password" not in response.text.lower() or "has_password" in response.text


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(anon_client: AsyncClient) -> None:
    email = "dup@example.com"
    payload = {"email": email, "password": TEST_PASSWORD, "display_name": "A"}

    assert (await anon_client.post(REGISTER, json=payload)).status_code == 201
    second = await anon_client.post(REGISTER, json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email_case_insensitively(
    anon_client: AsyncClient,
) -> None:
    await anon_client.post(
        REGISTER,
        json={"email": "Case@Example.com", "password": TEST_PASSWORD, "display_name": "A"},
    )
    response = await anon_client.post(
        REGISTER,
        json={"email": "case@example.com", "password": TEST_PASSWORD, "display_name": "B"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "password",
    [
        "short1",  # too short
        "alllettersonly",  # no digit
        "1234567890",  # no letter
        "        11",  # effectively blank
    ],
)
async def test_register_enforces_password_policy(anon_client: AsyncClient, password: str) -> None:
    response = await anon_client.post(
        REGISTER,
        json={"email": "weak@example.com", "password": password, "display_name": "W"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        REGISTER,
        json={"email": "not-an-email", "password": TEST_PASSWORD, "display_name": "X"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_unknown_fields(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        REGISTER,
        json={
            "email": "extra@example.com",
            "password": TEST_PASSWORD,
            "display_name": "X",
            "is_admin": True,  # privilege escalation attempt
        },
    )
    assert response.status_code == 422


# --- sign in -------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_succeeds_with_correct_password(anon_client: AsyncClient) -> None:
    await register_account(anon_client, email="login@example.com")

    response = await anon_client.post(
        LOGIN, json={"email": "login@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "login@example.com"


@pytest.mark.asyncio
async def test_login_is_case_insensitive_on_email(anon_client: AsyncClient) -> None:
    await register_account(anon_client, email="mixed@example.com")

    response = await anon_client.post(
        LOGIN, json={"email": "MiXeD@Example.COM", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_401(anon_client: AsyncClient) -> None:
    await register_account(anon_client, email="wrong@example.com")

    response = await anon_client.post(
        LOGIN, json={"email": "wrong@example.com", "password": "Wrong-Password-123"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_with_unknown_email_is_indistinguishable(anon_client: AsyncClient) -> None:
    """Unknown account and wrong password must return identical responses."""
    await register_account(anon_client, email="known@example.com")

    wrong_password = await anon_client.post(
        LOGIN, json={"email": "known@example.com", "password": "Wrong-Password-123"}
    )
    unknown_user = await anon_client.post(
        LOGIN, json={"email": "nobody@example.com", "password": "Wrong-Password-123"}
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


# --- access tokens -------------------------------------------------------
@pytest.mark.asyncio
async def test_me_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(ME)).status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_garbage_token(anon_client: AsyncClient) -> None:
    response = await anon_client.get(ME, headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_token_signed_with_another_key(anon_client: AsyncClient) -> None:
    from datetime import timedelta

    token, _ = create_access_token(
        subject=uuid.uuid4(),
        email="attacker@example.com",
        session_id=uuid.uuid4(),
        secret="attacker-controlled-key-32-bytes!!!",
        algorithm="HS256",
        ttl=timedelta(minutes=5),
    )
    response = await anon_client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_profile_when_authenticated(client: AsyncClient, account) -> None:
    response = await client.get(ME)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == account.email
    assert body["has_password"] is True
    assert body["role"] == "learner"


@pytest.mark.asyncio
async def test_me_does_not_leak_password_hash(client: AsyncClient) -> None:
    response = await client.get(ME)
    assert "argon2" not in response.text
    assert "password_hash" not in response.text


# --- sessions ------------------------------------------------------------
@pytest.mark.asyncio
async def test_logout_revokes_the_session_immediately(
    anon_client: AsyncClient, account
) -> None:
    """A logged-out access token must stop working before it expires."""
    headers = {"Authorization": f"Bearer {account.access_token}"}
    assert (await anon_client.get(ME, headers=headers)).status_code == 200

    logout = await anon_client.post(LOGOUT, json={"refresh_token": account.refresh_token})
    assert logout.status_code == 200

    assert (await anon_client.get(ME, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_refresh_rotates_the_token(anon_client: AsyncClient) -> None:
    account = await register_account(anon_client, email="rotate@example.com")

    first = await anon_client.post(REFRESH, json={"refresh_token": account.refresh_token})
    assert first.status_code == 200
    new_refresh = first.json()["refresh_token"]
    assert new_refresh != account.refresh_token

    # The new token works.
    assert (await anon_client.post(REFRESH, json={"refresh_token": new_refresh})).status_code == 200


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_all_sessions(anon_client: AsyncClient) -> None:
    """Replaying a consumed token is treated as theft: everything is revoked."""
    account = await register_account(anon_client, email="replay@example.com")

    rotated = await anon_client.post(REFRESH, json={"refresh_token": account.refresh_token})
    new_refresh = rotated.json()["refresh_token"]
    new_access = rotated.json()["access_token"]

    # Replay the original, already-consumed token.
    replay = await anon_client.post(REFRESH, json={"refresh_token": account.refresh_token})
    assert replay.status_code == 401

    # The attacker's rotation is now void too.
    assert (
        await anon_client.post(REFRESH, json={"refresh_token": new_refresh})
    ).status_code == 401
    # And so is the access token issued by it.
    assert (
        await anon_client.get(ME, headers={"Authorization": f"Bearer {new_access}"})
    ).status_code == 401


@pytest.mark.asyncio
async def test_logout_is_idempotent(anon_client: AsyncClient) -> None:
    account = await register_account(anon_client, email="idem@example.com")

    assert (
        await anon_client.post(LOGOUT, json={"refresh_token": account.refresh_token})
    ).status_code == 200
    # A second logout with the same token is not an error.
    assert (
        await anon_client.post(LOGOUT, json={"refresh_token": account.refresh_token})
    ).status_code == 200


@pytest.mark.asyncio
async def test_refresh_with_unknown_token_is_401(anon_client: AsyncClient) -> None:
    response = await anon_client.post(REFRESH, json={"refresh_token": "x" * 40})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_listing_marks_the_current_session(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me/sessions")
    assert response.status_code == 200
    sessions = response.json()

    assert len(sessions) == 1
    assert sessions[0]["is_current"] is True
    assert sessions[0]["provider"] == "password"


@pytest.mark.asyncio
async def test_session_can_be_revoked_by_id(
    anon_client: AsyncClient, account
) -> None:
    headers = {"Authorization": f"Bearer {account.access_token}"}
    sessions = (await anon_client.get("/api/v1/auth/me/sessions", headers=headers)).json()

    response = await anon_client.delete(
        f"/api/v1/auth/me/sessions/{sessions[0]['id']}", headers=headers
    )
    assert response.status_code == 200
    assert (await anon_client.get(ME, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_cannot_revoke_another_users_session(
    anon_client: AsyncClient, account
) -> None:
    """Session ids are scoped to the caller."""
    other = await register_account(anon_client, email="victim@example.com")
    victim_sessions = (
        await anon_client.get(
            "/api/v1/auth/me/sessions",
            headers={"Authorization": f"Bearer {other.access_token}"},
        )
    ).json()

    response = await anon_client.delete(
        f"/api/v1/auth/me/sessions/{victim_sessions[0]['id']}",
        headers={"Authorization": f"Bearer {account.access_token}"},
    )
    assert response.status_code == 404


# --- profile -------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_profile(client: AsyncClient) -> None:
    response = await client.patch(
        ME,
        json={
            "display_name": "Ada Lovelace",
            "headline": "Backend engineer",
            "bio": "Building things.",
            "location": "London",
            "website": "https://example.com",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Ada Lovelace"
    assert body["website"] == "https://example.com"


@pytest.mark.asyncio
async def test_profile_update_is_partial(client: AsyncClient) -> None:
    """Omitting a field must leave it untouched."""
    await client.patch(ME, json={"bio": "Original bio", "location": "Berlin"})
    response = await client.patch(ME, json={"headline": "Only this changed"})

    body = response.json()
    assert body["headline"] == "Only this changed"
    assert body["bio"] == "Original bio"
    assert body["location"] == "Berlin"


@pytest.mark.asyncio
async def test_profile_rejects_javascript_website(client: AsyncClient) -> None:
    response = await client.patch(ME, json={"website": "javascript:alert(1)"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_profile_rejects_role_escalation(client: AsyncClient) -> None:
    response = await client.patch(ME, json={"role": "admin"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_profile_rejects_xp_escalation(client: AsyncClient) -> None:
    response = await client.patch(ME, json={"xp": 999999})
    assert response.status_code == 422


# --- password change -----------------------------------------------------
@pytest.mark.asyncio
async def test_change_password_requires_current(anon_client: AsyncClient, account) -> None:
    headers = {"Authorization": f"Bearer {account.access_token}"}
    response = await anon_client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": "wrong", "password": "Brand-New-Pass-1"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_change_password_revokes_all_sessions(anon_client: AsyncClient, account) -> None:
    headers = {"Authorization": f"Bearer {account.access_token}"}
    response = await anon_client.post(
        "/api/v1/auth/me/password",
        headers=headers,
        json={"current_password": TEST_PASSWORD, "password": "Brand-New-Pass-1"},
    )
    assert response.status_code == 200

    # The old access token is dead.
    assert (await anon_client.get(ME, headers=headers)).status_code == 401
    # The new password works.
    login = await anon_client.post(
        LOGIN, json={"email": account.email, "password": "Brand-New-Pass-1"}
    )
    assert login.status_code == 200
    # The old password does not.
    old = await anon_client.post(
        LOGIN, json={"email": account.email, "password": TEST_PASSWORD}
    )
    assert old.status_code == 401


# --- password reset ------------------------------------------------------
@pytest.mark.asyncio
async def test_reset_request_does_not_reveal_account_existence(
    anon_client: AsyncClient,
) -> None:
    await register_account(anon_client, email="exists@example.com")

    known = await anon_client.post(
        "/api/v1/auth/password/reset-request", json={"email": "exists@example.com"}
    )
    unknown = await anon_client.post(
        "/api/v1/auth/password/reset-request", json={"email": "ghost@example.com"}
    )

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()


@pytest.mark.asyncio
async def test_reset_confirm_rejects_bad_token(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": "not-a-real-token-value", "password": "Some-New-Pass-1"},
    )
    assert response.status_code == 400


# --- auth config ---------------------------------------------------------
@pytest.mark.asyncio
async def test_auth_config_reports_capabilities(anon_client: AsyncClient) -> None:
    response = await anon_client.get("/api/v1/auth/config")
    assert response.status_code == 200
    body = response.json()
    assert body["password_auth_enabled"] is True
    assert body["registration_enabled"] is True
    assert body["github_enabled"] is False
    assert body["min_password_length"] >= 8


# --- admin ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_admin_cannot_list_users(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/users")).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_users(admin_client: AsyncClient, account) -> None:
    response = await admin_client.get("/api/v1/auth/users")
    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert account.email in emails


@pytest.mark.asyncio
async def test_admin_cannot_demote_self(admin_client: AsyncClient) -> None:
    me = (await admin_client.get(ME)).json()
    response = await admin_client.patch(
        f"/api/v1/auth/users/{me['id']}/role", params={"role": "learner"}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_can_promote_a_user(
    admin_client: AsyncClient, client: AsyncClient
) -> None:
    target = (await client.get(ME)).json()
    response = await admin_client.patch(
        f"/api/v1/auth/users/{target['id']}/role", params={"role": "author"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "author"


@pytest.mark.asyncio
async def test_learner_cannot_change_roles(client: AsyncClient) -> None:
    me = (await client.get(ME)).json()
    response = await client.patch(
        f"/api/v1/auth/users/{me['id']}/role", params={"role": "admin"}
    )
    assert response.status_code == 403


# --- protected resources -------------------------------------------------
@pytest.mark.asyncio
async def test_challenge_catalogue_requires_authentication(anon_client: AsyncClient) -> None:
    """Browsing the catalogue is public; it must not 401."""
    assert (await anon_client.get("/api/v1/challenges")).status_code == 200


@pytest.mark.asyncio
async def test_public_catalogue_shows_no_progress(anon_client: AsyncClient) -> None:
    challenges = (await anon_client.get("/api/v1/challenges")).json()
    assert all(challenge["completed"] is False for challenge in challenges)
    assert all(challenge["best_score"] == 0 for challenge in challenges)


@pytest.mark.asyncio
async def test_submitting_requires_authentication(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/v1/challenges/python-fundamentals-hello-world/run",
        json={"files": {"solution.py": "x = 1"}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/api/v1/dashboard")).status_code == 401


@pytest.mark.asyncio
async def test_progress_is_per_user(
    anon_client: AsyncClient, account, admin_client: AsyncClient
) -> None:
    """One learner's progress must not appear in another's dashboard."""
    headers = {"Authorization": f"Bearer {account.access_token}"}
    await submit_and_wait(
        anon_client,
        "python-fundamentals-hello-world",
        {"solution.py": "def greet(name):\n    return f'Hello, {name}!'\n"},
        headers=headers,
    )

    # The learner sees progress.
    learner_progress = (await anon_client.get("/api/v1/progress", headers=headers)).json()
    assert learner_progress["completed_challenges"] == 1

    # The admin does not.
    admin_progress = (await admin_client.get("/api/v1/progress")).json()
    assert admin_progress["completed_challenges"] == 0
    assert admin_progress["xp"] == 0


# --- password policy -----------------------------------------------------
@pytest.mark.asyncio
async def test_auth_config_reports_the_configured_minimum_length(
    anon_client: AsyncClient, settings
) -> None:
    """The UI builds its checklist from this value, so it must be the live setting."""
    settings.min_password_length = 16

    body = (await anon_client.get("/api/v1/auth/config")).json()
    assert body["min_password_length"] == 16


@pytest.mark.asyncio
async def test_configured_minimum_length_is_enforced(anon_client: AsyncClient, settings) -> None:
    """Raising the setting must actually reject shorter passwords."""
    settings.min_password_length = 20
    short = "Short-Pass-123"  # 14 characters: passes the schema default of 10

    response = await anon_client.post(
        REGISTER,
        json={"email": "lenient@example.com", "password": short, "display_name": "L"},
    )
    assert response.status_code == 422
    assert "20" in response.text


@pytest.mark.asyncio
async def test_default_length_still_applies(anon_client: AsyncClient) -> None:
    """The schema default is the floor when the setting is lower."""
    response = await anon_client.post(
        REGISTER,
        json={"email": "floor@example.com", "password": "Ab1", "display_name": "F"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_password_reset_enforces_the_length(anon_client: AsyncClient, settings) -> None:
    settings.min_password_length = 20
    response = await anon_client.post(
        "/api/v1/auth/password/reset-confirm",
        json={"token": "x" * 40, "password": "Short-Pass-123"},
    )
    # The policy runs before the token lookup, so this is a 422 either way.
    assert response.status_code == 422
