"""Application configuration.

All runtime configuration is sourced from environment variables (optionally via a
``.env`` file) so that the same image can run in development, CI and production.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, EnvSettingsSource, SettingsConfigDict

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Settings that hold a list, and the environment variable names they come from.
LIST_SETTINGS = frozenset({"cors_origins", "admin_emails"})


class _ListFriendlySource(EnvSettingsSource):
    """Accept comma-separated values for list settings, not only JSON.

    ``pydantic-settings`` treats a ``list[str]`` field as complex and tries to
    JSON-decode its value *before* any validator runs. A plain
    ``PYCRAFT_ADMIN_EMAILS=me@example.com`` — the form both ``.env.example`` and
    the deployment docs have always recommended — therefore fails at startup
    with a ``SettingsError``, and a ``field_validator(mode="before")`` cannot
    rescue it because it is never reached.

    Overriding the source rather than the field is what makes both spellings
    work: a comma-separated list is split, and anything starting with ``[`` is
    handed to the standard JSON path so existing deployments are unaffected.
    """

    def prepare_field_value(
        self,
        field_name: str,
        field: FieldInfo,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        if field_name in LIST_SETTINGS and isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return super().prepare_field_value(field_name, field, value, value_is_complex)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    """Runtime settings for the PyCraft API."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        env_prefix="PYCRAFT_",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: EnvSettingsSource,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Route environment and dotenv values through the list-aware source.

        Both are replaced, because a value can come from either: the environment
        in Docker, a ``.env`` file during local development.
        """
        return (
            init_settings,
            _ListFriendlySource(settings_cls),
            # DotEnvSettingsSource subclasses EnvSettingsSource, so rebuilding it
            # on the tolerant base keeps its file handling and gains the parsing.
            type(dotenv_settings)(
                settings_cls,
                env_file=dotenv_settings.env_file,
                env_file_encoding=dotenv_settings.env_file_encoding,
                case_sensitive=dotenv_settings.case_sensitive,
                env_prefix=dotenv_settings.env_prefix,
            ),
            file_secret_settings,
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
    # Run `alembic upgrade head` at startup. Convenient for development and for
    # a single-container deployment; turn it off when migrations are applied by
    # a release step, so a rollback is not fighting the app for the schema.
    auto_migrate: bool = True

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

    # --- AI assistance ---------------------------------------------------
    # "disabled" (default) | "openai" — the latter covers any OpenAI-compatible
    # /chat/completions endpoint (OpenAI, Groq, vLLM, Ollama, ...).
    ai_provider: Literal["disabled", "openai"] = "disabled"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_temperature: float = 0.4
    ai_timeout_seconds: float = 30.0
    ai_max_tokens: int = 700
    # Per-user, per-hour ceiling. Guards against a runaway client burning quota.
    ai_requests_per_hour: int = 40

    # --- Content ---------------------------------------------------------
    challenges_dir: Path = REPO_ROOT / "challenges"
    tutorials_dir: Path = REPO_ROOT / "tutorials"

    # --- Execution -------------------------------------------------------
    execution_backend: Literal["docker", "local"] = "docker"
    # Name of the image built from ``runner/Dockerfile``.
    runner_image: str = "pycraft-runner:3.12"
    docker_host: str | None = None
    # Ceiling applied regardless of what a challenge requests. A challenge can
    # lower these limits but never raise them.
    max_time_limit_ms: int = 10_000
    # Keeps one submission from harming the sandbox host or the API container.
    # Every challenge's ``memory_limit_mb`` is clamped to this (see
    # ``ExecutionLimits.clamped``), so it is the real per-submission ceiling
    # regardless of what content declares.
    #
    # Do not lower this below ~48 MB: CPython plus pytest alone need ~33 MB
    # before a single line of learner code runs, and the heaviest suite in
    # ``challenges/`` peaks near 46 MB. Below roughly 64 MB the platform starts
    # failing ordinary submissions rather than abusive ones.
    max_memory_limit_mb: int = 100
    max_output_bytes: int = 64 * 1024
    # Number of submissions that may run concurrently. Guards the host from a
    # submission storm; the queue upstream is intentionally simple for the MVP.
    execution_concurrency: int = 4

    # How many background workers drain the submission queue. Kept at or below
    # ``execution_concurrency`` so workers are not simply queueing on the
    # sandbox semaphore.
    worker_concurrency: int = 2
    # How long a worker's claim on a submission stays valid. Must comfortably
    # exceed the longest sandbox run, or a slow submission gets executed twice.
    worker_lease_seconds: int = 120
    # Run the workers inside the API process. Disable when workers are deployed
    # separately, so the API does not duplicate the work.
    run_workers_in_process: bool = True

    # --- Defaults for challenges lacking explicit limits -----------------
    default_time_limit_ms: int = 5_000
    # Matches the ceiling above, so the fallback never asks for more memory
    # than the platform will actually grant.
    default_memory_limit_mb: int = 100

    @field_validator("challenges_dir", "tutorials_dir", "database_url", mode="before")
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
    def ai_enabled(self) -> bool:
        """True only when a provider is selected *and* fully configured."""
        if self.ai_provider == "disabled":
            return False
        return bool(self.ai_api_key and self.ai_base_url and self.ai_model)

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
