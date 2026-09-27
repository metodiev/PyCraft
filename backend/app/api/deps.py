"""Shared FastAPI dependencies.

Authentication resolves a real user from a bearer access token. The token names
a session, which is checked against the database, so a logout or a password
change takes effect immediately rather than when the JWT happens to expire.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import TokenError, decode_access_token
from app.db.session import get_session
from app.execution.base import ExecutionBackend
from app.models import User
from app.models.roles import UserRole
from app.services.auth import AuthService
from app.services.challenges import ChallengeRepository
from app.services.email import EmailSender

SessionDep = Annotated[AsyncSession, Depends(get_session)]

# ``auto_error=False`` so failures raise our own consistent 401 shape.
_bearer = HTTPBearer(auto_error=False, description="JWT access token")


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_backend(request: Request) -> ExecutionBackend:
    backend = getattr(request.app.state, "execution_backend", None)
    if backend is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution backend is not available",
        )
    return backend


def get_repository(request: Request) -> ChallengeRepository:
    return request.app.state.challenges


def get_emailer(settings: SettingsDep) -> EmailSender:
    return EmailSender(settings)


def get_auth_service(
    session: SessionDep, settings: SettingsDep, emailer: EmailerDep
) -> AuthService:
    return AuthService(session, settings, emailer)


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
BackendDep = Annotated[ExecutionBackend, Depends(get_backend)]
RepositoryDep = Annotated[ChallengeRepository, Depends(get_repository)]
EmailerDep = Annotated[EmailSender, Depends(get_emailer)]
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def client_ip(request: Request, x_forwarded_for: Annotated[str | None, Header()] = None) -> str:
    """Best-effort client address, honouring the first proxy hop."""
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()[:64]
    if request.client is not None:
        return (request.client.host or "")[:64]
    return ""


IPDep = Annotated[str, Depends(client_ip)]
UserAgentDep = Annotated[str, Header(alias="User-Agent")]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    """Resolve the authenticated user, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    try:
        claims = decode_access_token(
            credentials.credentials,
            secret=settings.resolved_secret_key(),
            algorithm=settings.jwt_algorithm,
        )
    except TokenError as exc:
        raise _unauthorized(str(exc)) from exc

    # The session must still be live — this is what makes logout immediate.
    service = AuthService(session, settings, EmailSender(settings))
    if not await service.verify_session_active(claims.session_id):
        raise _unauthorized("Session has ended")

    user = await session.get(User, claims.subject)
    if user is None:
        raise _unauthorized("Account no longer exists")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled"
        )
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def optional_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User | None:
    """Resolve the user when a valid token is present, else ``None``.

    Used by endpoints that stay readable while logged out, such as the public
    challenge catalogue.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await current_user(session, settings, credentials)
    except HTTPException:
        return None


OptionalUser = Annotated[User | None, Depends(optional_user)]


async def _guard_author(user: CurrentUser) -> User:
    if not user.role.at_least(UserRole.AUTHOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the author role",
        )
    return user


async def _guard_admin(user: CurrentUser) -> User:
    if not user.role.at_least(UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the admin role",
        )
    return user


RequireAuthor = Annotated[User, Depends(_guard_author)]
RequireAdmin = Annotated[User, Depends(_guard_admin)]
