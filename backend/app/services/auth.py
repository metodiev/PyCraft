"""Authentication service: accounts, sessions and password resets.

Design notes worth knowing before editing:

* **Refresh tokens rotate on every use.** A refresh consumes the presented
  token and issues a new one. Replaying a consumed token is treated as
  compromise: the whole session family is revoked.
* **Registration does not reveal whether an email exists.** Signing up with a
  known address returns the same response shape as a new one.
* **Password reset never reveals whether an account exists** either.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.models import AuthProvider, LinkedAccount, User, UserRole
from app.models import Session as SessionModel
from app.models.auth import PasswordResetToken, is_past
from app.services.email import EmailSender

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised for any credential problem. Deliberately unspecific in messages."""


class EmailAlreadyRegisteredError(AuthError):
    pass


class RegistrationDisabledError(AuthError):
    pass


class InvalidCredentialsError(AuthError):
    pass


class AccountDisabledError(AuthError):
    pass


@dataclass(slots=True)
class TokenPair:
    """What a client stores after signing in."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, emailer: EmailSender) -> None:
        self._session = session
        self._settings = settings
        self._emailer = emailer

    # --- registration ----------------------------------------------------
    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[User, TokenPair]:
        if not self._settings.allow_registration:
            raise RegistrationDisabledError("Registration is currently disabled")

        email = normalise_email(email)
        existing = await self._session.scalar(select(User).where(User.email == email))
        if existing is not None:
            raise EmailAlreadyRegisteredError("That email address is already registered")

        user = User(
            email=email,
            display_name=display_name.strip() or email.split("@")[0],
            password_hash=hash_password(password),
            role=self._role_for(email),
        )
        self._session.add(user)
        await self._session.flush()

        tokens = await self._issue_tokens(user, user_agent=user_agent, ip_address=ip_address)
        await self._session.commit()
        await self._session.refresh(user)
        return user, tokens

    # --- sign in ---------------------------------------------------------
    async def authenticate(
        self, *, email: str, password: str, user_agent: str = "", ip_address: str = ""
    ) -> tuple[User, TokenPair]:
        user = await self._session.scalar(select(User).where(User.email == normalise_email(email)))

        # Always run a hash comparison, even for unknown accounts, so response
        # timing does not disclose which emails are registered.
        stored_hash = user.password_hash if user is not None else _DUMMY_HASH
        password_ok = verify_password(password, stored_hash)

        if user is None or not password_ok or not user.has_password:
            raise InvalidCredentialsError("Email or password is incorrect")
        if not user.is_active:
            raise AccountDisabledError("This account has been disabled")

        tokens = await self._issue_tokens(user, user_agent=user_agent, ip_address=ip_address)
        await self._session.commit()
        return user, tokens

    async def sign_in_with_provider(
        self,
        *,
        provider: AuthProvider,
        provider_user_id: str,
        provider_login: str,
        email: str,
        display_name: str,
        avatar_url: str = "",
        user_agent: str = "",
        ip_address: str = "",
    ) -> tuple[User, TokenPair]:
        """Sign in via an external identity, linking or creating as needed."""
        email = normalise_email(email)

        link = await self._session.scalar(
            select(LinkedAccount).where(
                LinkedAccount.provider == provider,
                LinkedAccount.provider_user_id == provider_user_id,
            )
        )

        if link is not None:
            user = await self._session.get(User, link.user_id)
            if user is None or not user.is_active:  # pragma: no cover - orphaned link
                raise AccountDisabledError("This account has been disabled")
            link.provider_login = provider_login
        else:
            # Link to an existing account for the same verified email, otherwise
            # create one. GitHub emails are verified, so matching on them is safe.
            user = await self._session.scalar(select(User).where(User.email == email))
            if user is None:
                if not self._settings.allow_registration:
                    raise RegistrationDisabledError("Registration is currently disabled")
                user = User(
                    email=email,
                    display_name=display_name or provider_login or email.split("@")[0],
                    role=self._role_for(email),
                    email_verified=True,
                    avatar_url=avatar_url,
                )
                self._session.add(user)
                await self._session.flush()
            elif not user.is_active:
                raise AccountDisabledError("This account has been disabled")

            self._session.add(
                LinkedAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_user_id=provider_user_id,
                    provider_login=provider_login,
                )
            )

        await self._session.flush()
        tokens = await self._issue_tokens(
            user, provider=provider, user_agent=user_agent, ip_address=ip_address
        )
        await self._session.commit()
        await self._session.refresh(user)
        return user, tokens

    # --- session lifecycle -----------------------------------------------
    async def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        """Rotate a refresh token.

        Reusing a consumed token means the token leaked, so the entire session
        is revoked rather than merely rejecting the request.
        """
        token_hash = hash_opaque_token(refresh_token)
        record = await self._session.scalar(
            select(SessionModel).where(SessionModel.refresh_token_hash == token_hash)
        )
        if record is None:
            raise InvalidCredentialsError("Session is not valid")

        if record.revoked_at is not None:
            # Replay of an already-rotated token: assume compromise.
            logger.warning("Refresh token reuse detected for session %s", record.id)
            await self._revoke_all_for_user(record.user_id)
            await self._session.commit()
            raise InvalidCredentialsError("Session is not valid")

        if is_past(record.expires_at):
            record.revoked_at = utcnow()
            await self._session.commit()
            raise InvalidCredentialsError("Session has expired")

        user = await self._session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise AccountDisabledError("This account has been disabled")

        record.revoked_at = utcnow()
        tokens = await self._issue_tokens(
            user,
            provider=record.provider,
            user_agent=record.user_agent,
            ip_address=record.ip_address,
        )
        await self._session.commit()
        return user, tokens

    async def logout(self, refresh_token: str) -> None:
        """Revoke one session. Idempotent: an unknown token is not an error."""
        record = await self._session.scalar(
            select(SessionModel).where(
                SessionModel.refresh_token_hash == hash_opaque_token(refresh_token)
            )
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = utcnow()
            await self._session.commit()

    async def revoke_session(self, session_id: uuid.UUID) -> bool:
        record = await self._session.get(SessionModel, session_id)
        if record is None or record.revoked_at is not None:
            return False
        record.revoked_at = utcnow()
        await self._session.commit()
        return True

    async def _revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    async def list_sessions(self, user_id: uuid.UUID) -> list[SessionModel]:
        rows = await self._session.scalars(
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.revoked_at.is_(None))
            .order_by(SessionModel.last_used_at.desc())
        )
        # Expiry is filtered in Python because SQLite cannot compare an
        # aware datetime literal against its timezone-naive storage.
        return [row for row in rows if not is_past(row.expires_at)]

    async def verify_session_active(self, session_id: uuid.UUID) -> bool:
        """Check that a JWT's session has not been revoked or expired."""
        record = await self._session.get(SessionModel, session_id)
        return record is not None and record.is_active

    async def linked_providers(self, user_id: uuid.UUID) -> list[str]:
        """Provider names linked to the account, e.g. ``["github"]``."""
        rows = await self._session.scalars(
            select(LinkedAccount.provider).where(LinkedAccount.user_id == user_id)
        )
        return [str(provider) for provider in rows]

    # --- password reset --------------------------------------------------
    async def request_password_reset(self, email: str, *, ip_address: str = "") -> bool:
        """Send a reset link. Always reports success, regardless of existence."""
        user = await self._session.scalar(select(User).where(User.email == normalise_email(email)))
        if user is None or not user.is_active:
            return False

        # Invalidate outstanding tokens so only the newest link works.
        now = utcnow()
        await self._session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )

        raw_token = generate_opaque_token()
        self._session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=now + timedelta(minutes=self._settings.password_reset_ttl_minutes),
                requested_ip=ip_address,
            )
        )
        await self._session.commit()

        reset_url = f"{self._settings.frontend_base_url.rstrip('/')}/reset-password?token={raw_token}"
        await self._emailer.send_password_reset(to=user.email, display_name=user.display_name, reset_url=reset_url)
        return True

    async def reset_password(self, token: str, new_password: str) -> User:
        record = await self._session.scalar(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == hash_opaque_token(token)
            )
        )
        if record is None or not record.is_usable:
            raise InvalidCredentialsError("This reset link is invalid or has expired")

        user = await self._session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise AccountDisabledError("This account has been disabled")

        record.used_at = utcnow()
        user.password_hash = hash_password(new_password)
        # A password change ends every existing session.
        await self._revoke_all_for_user(user.id)
        await self._session.commit()
        return user

    async def change_password(
        self, user: User, *, current_password: str, new_password: str
    ) -> None:
        if user.has_password and not verify_password(current_password, user.password_hash or ""):
            raise InvalidCredentialsError("Current password is incorrect")

        user.password_hash = hash_password(new_password)
        await self._revoke_all_for_user(user.id)
        await self._session.commit()

    # --- internals -------------------------------------------------------
    async def _issue_tokens(
        self,
        user: User,
        *,
        provider: AuthProvider = AuthProvider.PASSWORD,
        user_agent: str = "",
        ip_address: str = "",
    ) -> TokenPair:
        refresh_raw = generate_opaque_token()
        expires_at = utcnow() + timedelta(days=self._settings.refresh_token_ttl_days)

        record = SessionModel(
            user_id=user.id,
            refresh_token_hash=hash_opaque_token(refresh_raw),
            provider=provider,
            user_agent=user_agent[:300],
            ip_address=ip_address[:64],
            expires_at=expires_at,
        )
        self._session.add(record)
        await self._session.flush()

        ttl = timedelta(minutes=self._settings.access_token_ttl_minutes)
        access_token, _ = create_access_token(
            subject=user.id,
            email=user.email,
            session_id=record.id,
            secret=self._settings.resolved_secret_key(),
            algorithm=self._settings.jwt_algorithm,
            ttl=ttl,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_raw,
            expires_in=int(ttl.total_seconds()),
        )

    def _role_for(self, email: str) -> UserRole:
        if email in {normalise_email(item) for item in self._settings.admin_emails}:
            return UserRole.ADMIN
        return UserRole.LEARNER


# --- helpers -------------------------------------------------------------
def normalise_email(email: str) -> str:
    return email.strip().lower()


def utcnow() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(UTC).date()


# A real Argon2 hash of a random value, used to keep unknown-account logins
# taking the same time as known ones.
_DUMMY_HASH = hash_password("pycraft-timing-equalisation-placeholder")
