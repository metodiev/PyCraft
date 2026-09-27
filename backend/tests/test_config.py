"""Tests for settings parsing.

The list-valued settings are the reason this file exists. ``pydantic-settings``
treats ``list[str]`` as complex and JSON-decodes the environment value before any
validator runs, so ``PYCRAFT_ADMIN_EMAILS=me@example.com`` — the form the
deployment documentation and ``.env.example`` both recommend — used to abort
startup with a ``SettingsError``. The API container could not boot at all, which
is exactly the kind of failure a configuration test should catch.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings

# The environment variables under test, cleared before and after each case so a
# developer's real shell cannot influence the outcome.
LIST_VARIABLES = ("PYCRAFT_CORS_ORIGINS", "PYCRAFT_ADMIN_EMAILS")


@pytest.fixture
def clean_list_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Clear the list settings so a developer's shell cannot affect the result.

    Note that `Settings` also reads a `.env` file. None is committed and the
    suite does not create one, but if a developer has one locally it will take
    precedence over the values set here — so these tests could fail for a reason
    that is not the code.
    """
    for name in LIST_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_cors_origins_accepts_comma_separated(clean_list_env: pytest.MonkeyPatch) -> None:
    clean_list_env.setenv(
        "PYCRAFT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    )

    assert Settings().cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]


def test_admin_emails_accepts_comma_separated(clean_list_env: pytest.MonkeyPatch) -> None:
    clean_list_env.setenv("PYCRAFT_ADMIN_EMAILS", "me@example.com,you@example.com")

    assert Settings().admin_emails == ["me@example.com", "you@example.com"]


def test_single_value_becomes_a_one_item_list(clean_list_env: pytest.MonkeyPatch) -> None:
    """A lone origin is the common case, and must not need a trailing comma."""
    clean_list_env.setenv("PYCRAFT_CORS_ORIGINS", "http://localhost:5173")

    assert Settings().cors_origins == ["http://localhost:5173"]


def test_json_array_still_accepted(clean_list_env: pytest.MonkeyPatch) -> None:
    """Deployments already using the JSON form must keep working."""
    clean_list_env.setenv("PYCRAFT_ADMIN_EMAILS", '["a@example.com","b@example.com"]')

    assert Settings().admin_emails == ["a@example.com", "b@example.com"]


def test_whitespace_and_empty_entries_are_dropped(clean_list_env: pytest.MonkeyPatch) -> None:
    clean_list_env.setenv("PYCRAFT_ADMIN_EMAILS", " a@example.com , ,b@example.com ")

    assert Settings().admin_emails == ["a@example.com", "b@example.com"]


def test_unset_list_settings_default_to_empty(clean_list_env: pytest.MonkeyPatch) -> None:
    """No implicit admins: an unset list must not invent a value."""
    assert Settings().admin_emails == []
