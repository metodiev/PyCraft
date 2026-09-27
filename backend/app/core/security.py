"""Password hashing and token primitives.

Two token kinds with deliberately different properties:

* **Access token** — a short-lived, stateless JWT. Cheap to verify on every
  request, cannot be revoked before expiry, so it stays short-lived.
* **Refresh token** — an opaque random string, stored only as a hash. Revocable
  and rotating, so a leaked database dump does not yield usable tokens.

Passwords are hashed with Argon2id via ``pwdlib``, which also handles the
algorithm-migration path for us.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

# Argon2id with pwdlib's recommended parameters.
_password_hash = PasswordHash.recommended()

ACCESS_TOKEN_TYPE = "access"

# Refresh/reset tokens are random 32-byte strings; only their SHA-256 digest is
# persisted, so the plaintext exists solely in the client's hands.
_TOKEN_BYTES = 32


class TokenError(Exception):
    """Raised when a token is malformed, expired, or of the wrong type."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    """Verified contents of an access token."""

    subject: uuid.UUID
    email: str
    session_id: uuid.UUID
    expires_at: datetime


# --- passwords -----------------------------------------------------------
def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hash.verify(password, password_hash)
    except (UnknownHashError, ValueError):
        # A corrupt or legacy hash must read as "wrong password", never crash.
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the hash was produced with outdated parameters."""
    try:
        return _password_hash.verify_and_update("", password_hash)[1] is not None
    except Exception:  # pragma: no cover - defensive
        return False


# --- access tokens -------------------------------------------------------
def create_access_token(
    *,
    subject: uuid.UUID,
    email: str,
    session_id: uuid.UUID,
    secret: str,
    algorithm: str,
    ttl: timedelta,
) -> tuple[str, datetime]:
    """Return ``(token, expires_at)``."""
    now = datetime.now(UTC)
    expires_at = now + ttl
    payload: dict[str, Any] = {
        "sub": str(subject),
        "email": email,
        "sid": str(session_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token, expires_at


def decode_access_token(token: str, *, secret: str, algorithm: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(token, secret, algorithms=[algorithm], options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise TokenError("Unexpected token type")

    try:
        subject = uuid.UUID(str(payload["sub"]))
        session_id = uuid.UUID(str(payload.get("sid", "")))
    except (KeyError, ValueError) as exc:
        raise TokenError("Token payload is malformed") from exc

    return AccessTokenClaims(
        subject=subject,
        email=str(payload.get("email", "")),
        session_id=session_id,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )


# --- opaque tokens -------------------------------------------------------
def generate_opaque_token() -> str:
    """A high-entropy URL-safe token, safe to put in a link or response body."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_opaque_token(token: str) -> str:
    """Digest stored in the database.

    SHA-256 (not Argon2) is correct here: these tokens are already 256 bits of
    entropy, so the work factor only needs to stop a database dump from being
    replayed, and lookups must stay fast.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_equal(left: str, right: str) -> bool:
    """Constant-time comparison for any secret compared in application code."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
