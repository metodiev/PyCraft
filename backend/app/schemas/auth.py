"""Request/response schemas for authentication and profiles."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.roles import UserRole

# --- credentials ---------------------------------------------------------
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_BYTES = 1024  # Argon2 has no practical limit; this bounds abuse.
MAX_DISPLAY_NAME = 80
MAX_BIO = 600


class PasswordPolicy(BaseModel):
    """Base for models carrying a ``password`` field.

    Kept as a plain base class so the same rules apply to registration, reset
    and change-password without duplication.
    """

    password: str = Field(min_length=1)

    @field_validator("password")
    @classmethod
    def _check_password(cls, value: str) -> str:
        return validate_password(value)


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long")
    if password.strip() == "":
        raise ValueError("Password cannot be only whitespace")
    if not any(char.isalpha() for char in password):
        raise ValueError("Password must contain at least one letter")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must contain at least one number")
    return password


class RegisterRequest(PasswordPolicy):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    display_name: str = Field(default="", max_length=MAX_DISPLAY_NAME)

    @field_validator("display_name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=10)


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class PasswordResetConfirm(PasswordPolicy):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=10)


class ChangePasswordRequest(PasswordPolicy):
    model_config = ConfigDict(extra="forbid")

    current_password: str = ""


# --- responses -----------------------------------------------------------
class UserProfile(BaseModel):
    """Public-facing account details."""

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    avatar_url: str = ""
    headline: str = ""
    bio: str = ""
    location: str = ""
    website: str = ""
    xp: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_active_date: date | None = None
    is_admin: bool = False
    has_password: bool = False
    linked_providers: list[str] = Field(default_factory=list)
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class SessionInfo(BaseModel):
    """A signed-in device, for the "active sessions" list."""

    id: uuid.UUID
    provider: str
    user_agent: str
    ip_address: str
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    is_current: bool = False


class ProfileUpdate(BaseModel):
    """Editable profile fields. All optional; only provided keys are applied."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME)
    headline: str | None = Field(default=None, max_length=160)
    bio: str | None = Field(default=None, max_length=MAX_BIO)
    location: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=200)

    @field_validator("display_name", "headline", "location")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("website")
    @classmethod
    def _check_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return value
        value = value.strip()
        if not value.startswith(("http://", "https://")):
            raise ValueError("Website must start with http:// or https://")
        return value


class AuthConfigResponse(BaseModel):
    """What the sign-in page needs to render the right options."""

    password_auth_enabled: bool
    registration_enabled: bool
    github_enabled: bool
    min_password_length: int


class MessageResponse(BaseModel):
    message: str
