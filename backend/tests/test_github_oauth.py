"""GitHub OAuth: state integrity, redirect safety and identity mapping.

The network exchange with GitHub is not exercised here; these tests cover the
parts where a bug becomes a vulnerability — state forgery, open redirects, and
account-linking rules. ``_primary_verified_email`` is tested directly because
choosing an unverified address would let someone claim another user's account.
"""

from __future__ import annotations

import time

import httpx
import pytest
from app.core.config import Settings
from app.models import AuthProvider
from app.services import github_oauth
from app.services.github_oauth import OAuthError

STATE_SECRET = "test-key-at-least-32-bytes-long!!"


def oauth_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": "test",
        "secret_key": STATE_SECRET,
        "github_client_id": "client-id",
        "github_client_secret": "client-secret",
        "github_oauth_enabled": True,
        "frontend_base_url": "http://frontend.test",
        "oauth_redirect_base": "http://api.test",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# --- availability --------------------------------------------------------
def test_github_disabled_without_credentials() -> None:
    settings = Settings(environment="test", github_client_id="", github_client_secret="")
    assert settings.github_oauth_enabled is False
    assert github_oauth.github_available(settings) is False


def test_github_enabled_with_both_credentials() -> None:
    assert github_oauth.github_available(oauth_settings()) is True


# --- state ---------------------------------------------------------------
def test_state_roundtrip_preserves_redirect() -> None:
    settings = oauth_settings()
    state = github_oauth.build_state(settings, redirect_to="/challenges/abc")
    assert github_oauth.verify_state(settings, state) == "/challenges/abc"


def test_state_rejects_tampered_redirect() -> None:
    """State is signed, so an edited redirect must not survive verification."""
    settings = oauth_settings()
    state = github_oauth.build_state(settings, redirect_to="/")
    # Forge a new payload with an attacker-chosen redirect.
    forged = github_oauth.jwt.encode(
        {
            "type": github_oauth.STATE_TYPE,
            "n": "x",
            "redirect_to": "https://evil.example.com",
            "iat": int(time.time()),
            "exp": int(time.time()) + 600,
        },
        "attacker-key-not-the-real-one-but-long!!",
        algorithm="HS256",
    )
    with pytest.raises(OAuthError):
        github_oauth.verify_state(settings, forged)
    # The genuine one still works.
    assert github_oauth.verify_state(settings, state) == "/"


def test_state_rejects_expired_token() -> None:
    settings = oauth_settings()
    expired = github_oauth.jwt.encode(
        {
            "type": github_oauth.STATE_TYPE,
            "n": "x",
            "redirect_to": "/",
            "iat": int(time.time()) - 3600,
            "exp": int(time.time()) - 60,
        },
        STATE_SECRET,
        algorithm="HS256",
    )
    with pytest.raises(OAuthError, match="Invalid or expired"):
        github_oauth.verify_state(settings, expired)


def test_state_rejects_wrong_type() -> None:
    """An access token must not be usable as an OAuth state value."""
    import uuid
    from datetime import timedelta

    from app.core.security import create_access_token

    token, _ = create_access_token(
        subject=uuid.uuid4(),
        email="a@example.com",
        session_id=uuid.uuid4(),
        secret=STATE_SECRET,
        algorithm="HS256",
        ttl=timedelta(minutes=5),
    )
    with pytest.raises(OAuthError, match="Unexpected OAuth state type"):
        github_oauth.verify_state(oauth_settings(), token)


def test_state_rejects_garbage() -> None:
    with pytest.raises(OAuthError):
        github_oauth.verify_state(oauth_settings(), "not-a-jwt")


@pytest.mark.parametrize(
    "hostile",
    [
        "https://evil.example.com",
        "//evil.example.com",
        "http://evil.example.com/steal",
        "javascript:alert(1)",
    ],
)
def test_state_neutralises_open_redirect_attempts(hostile: str) -> None:
    """A hostile redirect target falls back to the site root."""
    settings = oauth_settings()
    state = github_oauth.build_state(settings, redirect_to=hostile)
    assert github_oauth.verify_state(settings, state) == "/"


def test_state_allows_nested_same_site_path() -> None:
    settings = oauth_settings()
    state = github_oauth.build_state(settings, redirect_to="/challenges/python-fundamentals-fizzbuzz")
    assert (
        github_oauth.verify_state(settings, state)
        == "/challenges/python-fundamentals-fizzbuzz"
    )


# --- urls ----------------------------------------------------------------
def test_authorize_url_contains_required_parameters() -> None:
    url = github_oauth.authorize_url(oauth_settings(), redirect_to="/")

    assert url.startswith(github_oauth.GITHUB_AUTHORIZE_URL)
    assert "client_id=client-id" in url
    assert "state=" in url
    assert "scope=read%3Auser+user%3Aemail" in url or "scope=" in url
    # The redirect target travels inside the signed state, never in the clear,
    # otherwise it could be edited by the user before returning.
    assert "redirect_to" not in url


def test_authorize_url_does_not_leak_the_client_secret() -> None:
    url = github_oauth.authorize_url(oauth_settings(), redirect_to="/")
    assert "client-secret" not in url


def test_callback_url_uses_configured_base() -> None:
    assert (
        github_oauth.callback_url(oauth_settings())
        == "http://api.test/api/v1/auth/github/callback"
    )


def test_error_url_targets_frontend_login() -> None:
    url = github_oauth.frontend_error_url(oauth_settings(), "Something went wrong")
    assert url.startswith("http://frontend.test/login?error=")


# --- email selection -----------------------------------------------------
async def _primary_email(emails: list[dict[str, object]]) -> str | None:
    """Drive ``_primary_verified_email`` with a stubbed GitHub response."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=emails)
    )
    async with httpx.AsyncClient(transport=transport) as client:
        return await github_oauth._primary_verified_email(client, {})


@pytest.mark.asyncio
async def test_prefers_primary_verified_email() -> None:
    email = await _primary_email(
        [
            {"email": "secondary@example.com", "primary": False, "verified": True},
            {"email": "primary@example.com", "primary": True, "verified": True},
        ]
    )
    assert email == "primary@example.com"


@pytest.mark.asyncio
async def test_ignores_unverified_primary_email() -> None:
    """Never trust an unverified address: it may belong to someone else."""
    email = await _primary_email(
        [
            {"email": "unverified@example.com", "primary": True, "verified": False},
            {"email": "verified@example.com", "primary": False, "verified": True},
        ]
    )
    assert email == "verified@example.com"


@pytest.mark.asyncio
async def test_returns_none_when_nothing_is_verified() -> None:
    assert await _primary_email([{"email": "a@example.com", "verified": False}]) is None
    assert await _primary_email([]) is None


@pytest.mark.asyncio
async def test_handles_malformed_email_payload() -> None:
    assert await _primary_email([{"nonsense": True}]) is None  # type: ignore[list-item]


# --- exchange ------------------------------------------------------------
@pytest.mark.asyncio
async def test_exchange_requires_configuration() -> None:
    settings = Settings(environment="test", github_client_id="", github_client_secret="")
    with pytest.raises(OAuthError, match="not configured"):
        await github_oauth.exchange_code_for_identity(settings, "code")


# --- account linking (via the auth service) ------------------------------
@pytest.mark.asyncio
async def test_github_signin_creates_account(anon_client) -> None:
    """A first-time GitHub user gets an account with no password."""
    from app.services.auth import AuthService
    from app.services.email import EmailSender

    settings = oauth_settings()
    # Use the application's own session factory via the running lifespan.
    import app.db.session as db_session

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        user, tokens = await github_oauth.sign_in(
            service,
            github_oauth.GitHubIdentity(
                user_id="12345",
                login="octocat",
                email="octocat@example.com",
                display_name="The Octocat",
                avatar_url="https://example.com/avatar.png",
            ),
        )
        assert user.email == "octocat@example.com"
        assert user.has_password is False
        assert user.avatar_url == "https://example.com/avatar.png"
        assert tokens.access_token


@pytest.mark.asyncio
async def test_github_signin_links_to_existing_email(anon_client) -> None:
    """Signing in with GitHub must not duplicate an existing account."""
    from app.services.auth import AuthService
    from app.services.email import EmailSender

    settings = oauth_settings()
    import app.db.session as db_session

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        # First: password registration.
        existing, _ = await service.register(
            email="linkme@example.com", password="Some-Password-123", display_name="Linker"
        )
        existing_id = existing.id

        # Then: GitHub sign-in with the same verified email.
        linked, _ = await github_oauth.sign_in(
            service,
            github_oauth.GitHubIdentity(
                user_id="999",
                login="linker",
                email="linkme@example.com",
                display_name="Linker on GitHub",
                avatar_url="",
            ),
        )

        assert linked.id == existing_id
        providers = await service.linked_providers(linked.id)
        assert "github" in providers


@pytest.mark.asyncio
async def test_github_signin_is_idempotent(anon_client) -> None:
    """Repeat sign-ins reuse the same account rather than creating more."""
    from app.services.auth import AuthService
    from app.services.email import EmailSender

    settings = oauth_settings()
    import app.db.session as db_session

    identity = github_oauth.GitHubIdentity(
        user_id="555",
        login="repeat",
        email="repeat@example.com",
        display_name="Repeat",
        avatar_url="",
    )

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        first, _ = await github_oauth.sign_in(service, identity)
        first_id = first.id

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        second, _ = await github_oauth.sign_in(service, identity)
        assert second.id == first_id


@pytest.mark.asyncio
async def test_github_identity_maps_provider_fields(anon_client) -> None:
    """The provider id is stored, so a renamed GitHub account still matches."""
    from app.services.auth import AuthService
    from app.services.email import EmailSender
    from sqlalchemy import select

    settings = oauth_settings()
    import app.db.session as db_session

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        await github_oauth.sign_in(
            service,
            github_oauth.GitHubIdentity(
                user_id="777",
                login="old-name",
                email="rename@example.com",
                display_name="Rename",
                avatar_url="",
            ),
        )

    async with db_session.get_session_factory()() as session:
        from app.models import LinkedAccount

        link = await session.scalar(
            select(LinkedAccount).where(LinkedAccount.provider_user_id == "777")
        )
        assert link is not None
        assert link.provider is AuthProvider.GITHUB
        assert link.provider_login == "old-name"


@pytest.mark.asyncio
async def test_disabled_account_cannot_sign_in_via_github(anon_client) -> None:
    from app.services.auth import AccountDisabledError, AuthService
    from app.services.email import EmailSender

    settings = oauth_settings()
    import app.db.session as db_session

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        user, _ = await service.register(
            email="disabled@example.com", password="Some-Password-123", display_name="D"
        )
        user.is_active = False
        await session.commit()

    async with db_session.get_session_factory()() as session:
        service = AuthService(session, settings, EmailSender(settings))
        with pytest.raises(AccountDisabledError):
            await github_oauth.sign_in(
                service,
                github_oauth.GitHubIdentity(
                    user_id="888",
                    login="disabled",
                    email="disabled@example.com",
                    display_name="D",
                    avatar_url="",
                ),
            )
