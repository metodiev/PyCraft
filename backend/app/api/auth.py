"""Authentication routes: register, sign in, refresh, logout, password reset."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import (
    AuthServiceDep,
    CurrentUser,
    IPDep,
    RequireAdmin,
    SessionDep,
    SettingsDep,
    UserAgentDep,
)
from app.models import User
from app.models.roles import UserRole
from app.schemas.auth import (
    AuthConfigResponse,
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    SessionInfo,
    TokenResponse,
    UserProfile,
)
from app.services.auth import (
    AccountDisabledError,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    RegistrationDisabledError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Deliberately uniform: never disclose whether an address is registered.
_RESET_ACK = "If that email address is registered, a reset link is on its way."


@router.get("/config", response_model=AuthConfigResponse, summary="Sign-in options")
async def auth_config(settings: SettingsDep) -> AuthConfigResponse:
    """Lets the UI hide options the deployment has disabled."""
    from app.schemas.auth import MIN_PASSWORD_LENGTH

    return AuthConfigResponse(
        password_auth_enabled=settings.allow_password_auth,
        registration_enabled=settings.allow_registration,
        github_enabled=settings.github_oauth_enabled,
        min_password_length=MIN_PASSWORD_LENGTH,
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
)
async def register(
    payload: RegisterRequest,
    auth: AuthServiceDep,
    settings: SettingsDep,
    ip: IPDep,
    user_agent: UserAgentDep = "",
) -> TokenResponse:
    if not settings.allow_password_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password sign-in is disabled. Use GitHub instead.",
        )
    try:
        user, tokens = await auth.register(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            user_agent=user_agent,
            ip_address=ip,
        )
    except RegistrationDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _token_response(user, tokens, await _providers_for(auth, user))


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(
    payload: LoginRequest,
    auth: AuthServiceDep,
    settings: SettingsDep,
    ip: IPDep,
    user_agent: UserAgentDep = "",
) -> TokenResponse:
    if not settings.allow_password_auth:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password sign-in is disabled. Use GitHub instead.",
        )
    try:
        user, tokens = await auth.authenticate(
            email=payload.email,
            password=payload.password,
            user_agent=user_agent,
            ip_address=ip,
        )
    except InvalidCredentialsError as exc:
        # Same response for unknown email and wrong password.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AccountDisabledError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    return _token_response(user, tokens, await _providers_for(auth, user))


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the session")
async def refresh_token(payload: RefreshRequest, auth: AuthServiceDep) -> TokenResponse:
    """Exchange a refresh token for a new pair. The old token is consumed."""
    try:
        user, tokens = await auth.refresh(payload.refresh_token)
    except (InvalidCredentialsError, AccountDisabledError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is no longer valid. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return _token_response(user, tokens, await _providers_for(auth, user))


@router.post("/logout", response_model=MessageResponse, summary="End this session")
async def logout(payload: RefreshRequest, auth: AuthServiceDep) -> MessageResponse:
    await auth.logout(payload.refresh_token)
    return MessageResponse(message="Signed out")


@router.get("/me", response_model=UserProfile, summary="Current account")
async def me(user: CurrentUser, auth: AuthServiceDep) -> UserProfile:
    return _profile(user, await _providers_for(auth, user))


@router.patch("/me", response_model=UserProfile, summary="Update profile")
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, session: SessionDep, auth: AuthServiceDep
) -> UserProfile:
    # ``exclude_unset`` distinguishes "not provided" from "set to empty string",
    # so a client can clear a field but cannot accidentally wipe the others.
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    return _profile(user, await _providers_for(auth, user))


@router.post("/me/password", response_model=MessageResponse, summary="Change password")
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, auth: AuthServiceDep
) -> MessageResponse:
    try:
        await auth.change_password(
            user, current_password=payload.current_password, new_password=payload.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    # Every session, including this one, was revoked.
    return MessageResponse(message="Password changed. Please sign in again.")


@router.get("/me/sessions", response_model=list[SessionInfo], summary="Active sessions")
async def list_sessions(
    user: CurrentUser,
    auth: AuthServiceDep,
    session: SessionDep,
    settings: SettingsDep,
    request: Request,
) -> list[SessionInfo]:
    rows = await auth.list_sessions(user.id)
    current_id = _current_session_id(request, settings)
    return [
        SessionInfo(
            id=row.id,
            provider=str(row.provider),
            user_agent=row.user_agent,
            ip_address=row.ip_address,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            is_current=row.id == current_id,
        )
        for row in rows
    ]


@router.delete(
    "/me/sessions/{session_id}",
    response_model=MessageResponse,
    summary="Revoke a session",
)
async def revoke_session(
    session_id: uuid.UUID, user: CurrentUser, auth: AuthServiceDep, session: SessionDep
) -> MessageResponse:
    rows = await auth.list_sessions(user.id)
    if not any(row.id == session_id for row in rows):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await auth.revoke_session(session_id)
    return MessageResponse(message="Session revoked")


@router.post(
    "/password/reset-request",
    response_model=MessageResponse,
    summary="Request a password reset link",
)
async def request_password_reset(
    payload: PasswordResetRequest, auth: AuthServiceDep, ip: IPDep
) -> MessageResponse:
    await auth.request_password_reset(payload.email, ip_address=ip)
    return MessageResponse(message=_RESET_ACK)


@router.post(
    "/password/reset-confirm",
    response_model=MessageResponse,
    summary="Complete a password reset",
)
async def confirm_password_reset(
    payload: PasswordResetConfirm, auth: AuthServiceDep
) -> MessageResponse:
    try:
        await auth.reset_password(payload.token, payload.password)
    except (InvalidCredentialsError, AccountDisabledError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MessageResponse(message="Password updated. You can sign in now.")


# --- admin ---------------------------------------------------------------
@router.get("/users", summary="List accounts (admin)")
async def list_users(admin: RequireAdmin, session: SessionDep) -> list[UserProfile]:
    from sqlalchemy import select

    rows = await session.scalars(select(User).order_by(User.created_at.desc()).limit(200))
    return [_profile(row, []) for row in rows]


@router.patch("/users/{user_id}/role", response_model=UserProfile, summary="Change a role (admin)")
async def set_user_role(
    user_id: uuid.UUID,
    role: UserRole,
    admin: RequireAdmin,
    session: SessionDep,
) -> UserProfile:
    target = await session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == admin.id and role is not UserRole.ADMIN:
        # Prevent locking yourself out of the admin area.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot demote your own account"
        )
    target.role = role
    await session.commit()
    await session.refresh(target)
    return _profile(target, [])


# --- helpers -------------------------------------------------------------
def _profile(user: User, providers: list[str]) -> UserProfile:
    return UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        avatar_url=user.avatar_url,
        headline=user.headline,
        bio=user.bio,
        location=user.location,
        website=user.website,
        xp=user.xp,
        current_streak=user.current_streak,
        longest_streak=user.longest_streak,
        last_active_date=user.last_active_date,
        is_admin=user.is_admin,
        has_password=user.has_password,
        linked_providers=providers,
        created_at=user.created_at,
    )


def _token_response(user: User, tokens, providers: list[str]) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        user=_profile(user, providers),
    )


async def _providers_for(auth: AuthServiceDep, user: User) -> list[str]:
    return await auth.linked_providers(user.id)


def _current_session_id(request: Request, settings: SettingsDep) -> uuid.UUID | None:
    """Identify which listed session the caller is currently using."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    from app.core.security import TokenError, decode_access_token

    try:
        claims = decode_access_token(
            header[7:].strip(),
            secret=settings.resolved_secret_key(),
            algorithm=settings.jwt_algorithm,
        )
    except TokenError:
        return None
    return claims.session_id


__all__ = ["router"]
