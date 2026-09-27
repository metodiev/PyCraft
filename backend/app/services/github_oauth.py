"""GitHub OAuth sign-in.

Flow (authorization code):

1. The browser is sent to ``/auth/github/authorize``.
2. We redirect to GitHub with a signed, time-limited ``state`` value.
3. GitHub returns to ``/auth/github/callback`` with ``code`` and ``state``.
4. We verify ``state``, exchange ``code`` for a token, read the profile, then
   sign the user in and redirect to the frontend with tokens in the URL
   **fragment** (fragments are not sent to servers and are stripped by the
   frontend as soon as they are read).

``state`` is a signed JWT rather than a stored opaque value: it needs to be
verifiable without a database round trip, and signing gives tamper-evidence for
free. It carries the post-login redirect target.
"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import Settings
from app.models import AuthProvider
from app.services.auth import AuthService, TokenPair

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

# ``state`` is short-lived: it only has to survive the user's trip to GitHub.
STATE_TTL_SECONDS = 600
STATE_TYPE = "github_oauth_state"

# Scopes: read the profile and the verified email address.
SCOPES = "read:user user:email"


class OAuthError(Exception):
    """Raised when the OAuth exchange fails."""


@dataclass(frozen=True, slots=True)
class GitHubIdentity:
    """The subset of a GitHub profile PyCraft uses."""

    user_id: str
    login: str
    email: str
    display_name: str
    avatar_url: str


def github_available(settings: Settings) -> bool:
    return settings.github_oauth_enabled


# --- state ---------------------------------------------------------------
def build_state(settings: Settings, *, redirect_to: str = "/") -> str:
    payload = {
        "type": STATE_TYPE,
        "n": secrets.token_urlsafe(16),
        "redirect_to": redirect_to[:300],
        "iat": int(time.time()),
        "exp": int(time.time()) + STATE_TTL_SECONDS,
    }
    return jwt.encode(
        payload, settings.resolved_secret_key(), algorithm=settings.jwt_algorithm
    )


def verify_state(settings: Settings, state: str) -> str:
    """Validate the state token and return the redirect target."""
    try:
        payload = jwt.decode(
            state,
            settings.resolved_secret_key(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp"]},
        )
    except jwt.InvalidTokenError as exc:
        raise OAuthError("Invalid or expired OAuth state") from exc

    if payload.get("type") != STATE_TYPE:
        raise OAuthError("Unexpected OAuth state type")
    redirect_to = str(payload.get("redirect_to", "/"))
    # Only allow same-site paths, never an absolute URL: an attacker must not be
    # able to turn the callback into an open redirect.
    if not redirect_to.startswith("/") or redirect_to.startswith("//"):
        return "/"
    return redirect_to


def authorize_url(settings: Settings, *, redirect_to: str = "/") -> str:
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": callback_url(settings),
        "scope": SCOPES,
        "state": build_state(settings, redirect_to=redirect_to),
        "allow_signup": "true",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def callback_url(settings: Settings) -> str:
    base = settings.oauth_redirect_base.rstrip("/")
    return f"{base}{settings.api_prefix}/auth/github/callback"


def frontend_error_url(settings: Settings, reason: str) -> str:
    base = settings.frontend_base_url.rstrip("/")
    return f"{base}/login?error={urlencode({'reason': reason})}"


# --- exchange ------------------------------------------------------------
async def exchange_code_for_identity(settings: Settings, code: str) -> GitHubIdentity:
    """Trade an authorization code for the user's GitHub identity."""
    if not github_available(settings):
        raise OAuthError("GitHub sign-in is not configured")

    async with httpx.AsyncClient(timeout=15.0) as client:
        token_response = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "redirect_uri": callback_url(settings),
            },
        )
        if token_response.status_code != 200:
            raise OAuthError("GitHub rejected the authorization code")

        token_body = token_response.json()
        access_token = token_body.get("access_token")
        if not access_token:
            # GitHub returns 200 with an ``error`` body on bad codes.
            raise OAuthError(str(token_body.get("error_description") or "No access token returned"))

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        profile_response = await client.get(GITHUB_USER_URL, headers=headers)
        if profile_response.status_code != 200:
            raise OAuthError("Unable to read the GitHub profile")
        profile = profile_response.json()

        email = profile.get("email")
        if not email:
            # The public profile often hides the email; the dedicated endpoint
            # exposes verified addresses to us because of the user:email scope.
            email = await _primary_verified_email(client, headers)

    if not email:
        raise OAuthError(
            "GitHub did not provide a verified email address. "
            "Make sure one is verified in your GitHub settings."
        )

    return GitHubIdentity(
        user_id=str(profile.get("id", "")),
        login=str(profile.get("login", "")),
        email=str(email),
        display_name=str(profile.get("name") or profile.get("login") or ""),
        avatar_url=str(profile.get("avatar_url") or ""),
    )


async def _primary_verified_email(client: httpx.AsyncClient, headers: dict[str, str]) -> str | None:
    response = await client.get(GITHUB_EMAILS_URL, headers=headers)
    if response.status_code != 200:
        return None
    emails = response.json()
    if not isinstance(emails, list):
        return None

    # Prefer the primary verified address, then any verified one.
    for candidate in emails:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("primary") and candidate.get("verified") and candidate.get("email"):
            return str(candidate["email"])
    for candidate in emails:
        if isinstance(candidate, dict) and candidate.get("verified") and candidate.get("email"):
            return str(candidate["email"])
    return None


async def sign_in(service: AuthService, identity: GitHubIdentity, **session_kwargs) -> tuple[object, TokenPair]:
    """Create or link the account and start a session."""
    return await service.sign_in_with_provider(
        provider=AuthProvider.GITHUB,
        provider_user_id=identity.user_id,
        provider_login=identity.login,
        email=identity.email,
        display_name=identity.display_name,
        avatar_url=identity.avatar_url,
        **session_kwargs,
    )
