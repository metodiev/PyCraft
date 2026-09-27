"""Application configuration.

All runtime configuration is sourced from environment variables (optionally via a
``.env`` file) so that the same image can run in development, CI and production.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Runtime settings for the PyCraft API."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_prefix="PYCRAFT_",
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- Persistence -----------------------------------------------------
    # SQLite keeps the local developer experience zero-setup; docker-compose and
    # production point this at PostgreSQL (postgresql+asyncpg://...).
    database_url: str = f"sqlite+aiosqlite:///{REPO_ROOT / 'backend' / '.pycraft.db'}"
    db_echo: bool = False
    db_pool_size: int = 5

    # --- Authentication --------------------------------------------------
    # Signing key for access tokens. Development generates a random key per
    # process (tokens do not survive a restart); production MUST set this, and
    # startup fails if it is missing.
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    password_reset_ttl_minutes: int = 60
    min_password_length: int = 10

    # Email/password sign-in. Disable to run OAuth-only.
    allow_password_auth: bool = True
    # Anyone can register. Disable to make the platform invite-only.
    allow_registration: bool = True
    # Emails listed here get the admin role on registration, enabling the
    # authoring UI. Empty by default: no implicit admins.
    admin_emails: list[str] = Field(default_factory=list)

    # --- GitHub OAuth ----------------------------------------------------
    github_client_id: str = ""
    github_client_secret: str = ""
    # Where GitHub redirects back to. Must match the registered callback.
    oauth_redirect_base: str = "http://127.0.0.1:8000"

    # --- Email -----------------------------------------------------------
    # "console" logs reset links instead of sending them (development default).
    # "smtp" delivers real mail using the settings below.
    email_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "PyCraft <noreply@pycraft.dev>"
    smtp_starttls: bool = True
    # Base URL the frontend is served from, used to build links in emails.
    frontend_base_url: str = "http://127.0.0.1:5173"

    # --- Content ---------------------------------------------------------
    challenges_dir: Path = REPO_ROOT / "challenges"

    # --- Execution -------------------------------------------------------
    execution_backend: Literal["docker", "local"] = "docker"
    # Name of the image built from ``runner/Dockerfile``.
    runner_image: str = "pycraft-runner:3.12"
    docker_host: str | None = None
    # Ceiling applied regardless of what a challenge requests. A challenge can
    # lower these limits but never raise them.
    max_time_limit_ms: int = 10_000
    max_memory_limit_mb: int = 512
    max_output_bytes: int = 64 * 1024
    # Number of submissions that may run concurrently. Guards the host from a
    # submission storm; the queue upstream is intentionally simple for the MVP.
    execution_concurrency: int = 4

    # --- Defaults for challenges lacking explicit limits -----------------
    default_time_limit_ms: int = 5_000
    default_memory_limit_mb: int = 128

    @field_validator("challenges_dir", "database_url", mode="before")
    @classmethod
    def _expand_user(cls, value: object) -> object:
        if isinstance(value, str):
            return str(value).replace("~", str(Path.home()))
        return value

    @field_validator("cors_origins", "admin_emails", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def resolved_secret_key(self) -> str:
        """Return the JWT signing key.

        Falls back to an ephemeral per-process key so development works with no
        configuration. A production instance without an explicit key is a
        misconfiguration and refuses to start rather than silently signing
        tokens with a key that changes on restart.
        """
        if self.secret_key:
            return self.secret_key
        if self.is_production:
            raise RuntimeError(
                "PYCRAFT_SECRET_KEY must be set in production. Generate one with:\n"
                "  python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        global _EPHEMERAL_SECRET
        if _EPHEMERAL_SECRET is None:
            import secrets as _secrets

            _EPHEMERAL_SECRET = _secrets.token_urlsafe(48)
            logger.warning(
                "PYCRAFT_SECRET_KEY is unset — using an ephemeral key. Access tokens "
                "will be invalidated on restart. Set PYCRAFT_SECRET_KEY to persist "
                "sessions across restarts."
            )
        return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
