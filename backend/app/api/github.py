"""GitHub OAuth routes.

These are browser-navigated endpoints, not API calls: they respond with
redirects. Tokens are handed to the frontend in the URL **fragment**, which is
never transmitted to a server and is stripped by the frontend immediately.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import AuthServiceDep, IPDep, SettingsDep, UserAgentDep
from app.services import github_oauth
from app.services.github_oauth import OAuthError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["auth"])


@router.get("/authorize", summary="Start GitHub sign-in")
async def authorize(
    settings: SettingsDep,
    redirect_to: str = "/",
) -> RedirectResponse:
    """Redirect the browser to GitHub.

    ``redirect_to`` is passed through the signed state value, so it cannot be
    tampered with, and is validated as a same-site path on return.
    """
    if not github_oauth.github_available(settings):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="GitHub sign-in is not configured on this deployment",
        )
    return RedirectResponse(github_oauth.authorize_url(settings, redirect_to=redirect_to), status_code=302)


@router.get("/callback", summary="Handle the GitHub redirect")
async def callback(
    code: str,
    state: str,
    auth: AuthServiceDep,
    settings: SettingsDep,
    ip: IPDep,
    user_agent: UserAgentDep = "",
) -> RedirectResponse:
    """Finish the OAuth exchange and land the user back in the app."""
    try:
        redirect_to = github_oauth.verify_state(settings, state)
    except OAuthError as exc:
        logger.warning("Rejected OAuth callback: %s", exc)
        # A bad state often means the page sat open too long, so say so.
        return RedirectResponse(
            github_oauth.frontend_error_url(settings, "Your sign-in link expired. Please try again."),
            status_code=302,
        )

    try:
        identity = await github_oauth.exchange_code_for_identity(settings, code)
        user, tokens = await github_oauth.sign_in(
            auth, identity, user_agent=user_agent, ip_address=ip
        )
    except OAuthError as exc:
        logger.warning("GitHub sign-in failed: %s", exc)
        return RedirectResponse(github_oauth.frontend_error_url(settings, str(exc)), status_code=302)
    except Exception:
        logger.exception("Unexpected error during GitHub sign-in")
        return RedirectResponse(
            github_oauth.frontend_error_url(settings, "GitHub sign-in failed. Please try again."),
            status_code=302,
        )

    fragment = urlencode(
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
        }
    )
    target = f"{settings.frontend_base_url.rstrip('/')}{redirect_to}#{fragment}"
    logger.info("GitHub sign-in succeeded for %s", getattr(user, "email", "?"))
    return RedirectResponse(target, status_code=302)


@router.get("/status", summary="Is GitHub sign-in available?")
async def github_status(settings: SettingsDep, request: Request) -> dict[str, object]:
    return {
        "enabled": github_oauth.github_available(settings),
        "authorize_url": "/api/v1/auth/github/authorize",
    }
