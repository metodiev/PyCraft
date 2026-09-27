"""AI assistance: the solution-leak guard, prompts, and endpoints.

The most important tests here are the sanitiser and the "disabled by default"
behaviour. The platform's promise is that AI scaffolds learning rather than
replacing it, so a regression that leaks a pasteable solution must fail CI.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.services.ai import (
    AIUnavailableError,
    ChatMessage,
    NullProvider,
    build_provider,
    explanation_messages,
    hint_messages,
    recommendation_messages,
    review_messages,
    sanitise,
)
from httpx import AsyncClient

CHALLENGE = "python-fundamentals-hello-world"
STATUS = "/api/v1/ai/status"
HINT = "/api/v1/ai/hint"
EXPLAIN = "/api/v1/ai/explain"
REVIEW = "/api/v1/ai/review"
RECOMMEND = "/api/v1/ai/recommend"


# --- provider selection --------------------------------------------------
def test_ai_is_disabled_by_default() -> None:
    """A fresh deployment must not silently call an external service."""
    settings = Settings(environment="test")
    assert settings.ai_provider == "disabled"
    assert settings.ai_enabled is False
    assert isinstance(build_provider(settings), NullProvider)


def test_enabling_a_provider_without_a_key_stays_disabled() -> None:
    settings = Settings(environment="test", ai_provider="openai", ai_api_key="")
    assert settings.ai_enabled is False


def test_provider_enabled_only_when_fully_configured() -> None:
    settings = Settings(
        environment="test", ai_provider="openai", ai_api_key="key", ai_model="model"
    )
    assert settings.ai_enabled is True
    assert build_provider(settings).name == "openai"


@pytest.mark.asyncio
async def test_null_provider_raises_rather_than_inventing_output() -> None:
    with pytest.raises(AIUnavailableError, match="not configured"):
        await NullProvider().complete([ChatMessage("user", "hi")])


# --- solution-leak filtering ---------------------------------------------
def test_plain_prose_passes_through() -> None:
    text = "Consider what happens when the name is empty. Which branch handles that?"
    cleaned, filtered = sanitise(text)

    assert cleaned == text
    assert filtered is False


def test_fenced_code_block_is_removed() -> None:
    """A pasteable block is the exact failure mode the platform must prevent."""
    text = "Try something like this:\n\n```python\ndef greet(name):\n    return f'Hello, {name}!'\n```\n\nBut think about the edge cases."

    cleaned, filtered = sanitise(text)

    assert "def greet" not in cleaned
    assert "```" not in cleaned
    assert filtered is True
    # Surrounding guidance survives.
    assert "Try something like this" in cleaned
    assert "edge cases" in cleaned


def test_inline_code_is_preserved() -> None:
    """Hints legitimately name functions and values inline."""
    text = "Look at how `greet` builds the string, and whether `name` can be empty."
    cleaned, filtered = sanitise(text)

    assert "`greet`" in cleaned
    assert filtered is False


def test_multiple_code_blocks_are_all_removed() -> None:
    text = "First:\n```\ncode one\n```\nThen:\n```python\ncode two\n```\nDone."

    cleaned, filtered = sanitise(text)

    assert "code one" not in cleaned
    assert "code two" not in cleaned
    assert "First:" in cleaned
    assert "Done." in cleaned
    assert filtered is True


def test_unclosed_code_block_still_removes_the_body() -> None:
    """A truncated response must not leak the code it did include."""
    text = "Try this:\n```python\ndef greet(name):\n    return name\n"

    cleaned, _ = sanitise(text)

    assert "def greet" not in cleaned


def test_solution_phrasing_is_flagged() -> None:
    _, filtered = sanitise("Here is the complete solution to your problem.")
    assert filtered is True


@pytest.mark.parametrize(
    "phrase",
    [
        "Here is the full solution.",
        "The complete implementation is below.",
        "You can copy and paste this into the editor.",
    ],
)
def test_each_solution_phrase_is_flagged(phrase: str) -> None:
    _, filtered = sanitise(phrase)
    assert filtered is True


def test_empty_input_is_handled() -> None:
    cleaned, filtered = sanitise("")
    assert cleaned == ""
    assert filtered is False


def test_excess_blank_lines_are_collapsed() -> None:
    cleaned, _ = sanitise("One.\n\n\n\n\nTwo.")
    assert cleaned == "One.\n\nTwo."


def test_sanitise_preserves_meaningful_content() -> None:
    long_text = "Think about the iterator protocol. " * 20
    cleaned, _ = sanitise(long_text)
    assert len(cleaned) > 400


# --- prompt construction -------------------------------------------------
def test_system_prompt_forbids_solutions() -> None:
    messages = hint_messages(
        challenge_title="Hello",
        description="Do the thing.",
        code="def f(): pass",
        authored_hints=[],
        attempt_number=1,
    )
    system = messages[0]
    assert system.role == "system"
    assert "NEVER write a complete solution" in system.content
    assert "no code blocks" in system.content.lower() or "fenced code blocks" in system.content.lower()


def test_hint_prompt_includes_authored_hints() -> None:
    """Generated hints must build on the author's material, not invent a path."""
    messages = hint_messages(
        challenge_title="Hello",
        description="Do the thing.",
        code="def greet(name): pass",
        authored_hints=["Use an f-string", "Return, do not print"],
        attempt_number=1,
    )
    user = messages[-1].content

    assert "Use an f-string" in user
    assert "Return, do not print" in user


def test_hint_prompt_escalates_with_attempt_number() -> None:
    first = hint_messages(
        challenge_title="T", description="D", code="", authored_hints=[], attempt_number=1
    )
    later = hint_messages(
        challenge_title="T", description="D", code="", authored_hints=[], attempt_number=5
    )

    assert "gentle nudge" in first[-1].content
    assert "more concrete" in later[-1].content


def test_hint_prompt_handles_no_authored_hints() -> None:
    messages = hint_messages(
        challenge_title="T", description="D", code="", authored_hints=[], attempt_number=1
    )
    assert "(none authored)" in messages[-1].content


def test_hint_prompt_truncates_huge_input() -> None:
    """A learner can paste megabytes; prompts must stay bounded."""
    messages = hint_messages(
        challenge_title="T",
        description="D" * 100_000,
        code="c" * 100_000,
        authored_hints=[],
        attempt_number=1,
    )
    user = messages[-1].content
    assert len(user) < 10_000


def test_explain_prompt_includes_the_error() -> None:
    messages = explanation_messages(
        challenge_title="T", error_text="AssertionError: assert 'nope' == 'Hello'", code="x = 1"
    )
    assert "AssertionError" in messages[-1].content
    assert "Do not provide corrected code" in messages[-1].content


def test_review_prompt_asks_for_observations_not_rewrites() -> None:
    messages = review_messages(challenge_title="T", code="def f(): pass")
    assert "Do not rewrite the code" in messages[-1].content
    assert "def f(): pass" in messages[-1].content


def test_recommendation_prompt_includes_weak_skills() -> None:
    messages = recommendation_messages(
        level_label="Junior",
        completed=3,
        total=20,
        weak_skills=["Async Python", "Testing"],
        recent_titles=["Hello, World"],
    )
    content = messages[-1].content
    assert "Async Python" in content
    assert "Junior" in content
    assert "3 of 20" in content


def test_recommendation_prompt_handles_a_blank_record() -> None:
    messages = recommendation_messages(
        level_label="Junior", completed=0, total=0, weak_skills=[], recent_titles=[]
    )
    content = messages[-1].content
    assert "nothing yet" in content
    assert "none identified yet" in content


# --- endpoints: disabled by default --------------------------------------
@pytest.mark.asyncio
async def test_ai_status_requires_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.get(STATUS)).status_code == 401


@pytest.mark.asyncio
async def test_ai_status_reports_disabled(client: AsyncClient) -> None:
    body = (await client.get(STATUS)).json()
    assert body["enabled"] is False
    assert body["provider"] == "disabled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "payload"),
    [
        (HINT, {"challenge_id": CHALLENGE, "code": "x = 1"}),
        (EXPLAIN, {"challenge_id": CHALLENGE, "error_text": "boom"}),
        (REVIEW, {"challenge_id": CHALLENGE, "code": "x = 1"}),
        (RECOMMEND, {}),
    ],
)
async def test_ai_endpoints_fail_clearly_when_disabled(
    client: AsyncClient, url: str, payload: dict
) -> None:
    """A clear 503 beats a confusing empty response."""
    response = await client.post(url, json=payload)
    assert response.status_code == 503
    assert "not enabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ai_endpoints_require_authentication(anon_client: AsyncClient) -> None:
    assert (await anon_client.post(RECOMMEND, json={})).status_code == 401


# --- endpoints: enabled, with a stubbed provider -------------------------
@pytest.fixture
def ai_settings(settings: Settings) -> Settings:
    settings.ai_provider = "openai"
    settings.ai_api_key = "test-key"
    settings.ai_base_url = "https://example.invalid/v1"
    settings.ai_model = "test-model"
    return settings


def _stub_provider(monkeypatch: pytest.MonkeyPatch, reply: str) -> list[list[ChatMessage]]:
    """Replace the provider with one that records prompts and returns a fixed reply."""
    captured: list[list[ChatMessage]] = []

    class StubProvider:
        name = "stub"
        available = True

        async def complete(self, messages, *, max_tokens: int = 700) -> str:
            captured.append(list(messages))
            return reply

    import app.api.ai as ai_module

    monkeypatch.setattr(ai_module, "build_provider", lambda _settings: StubProvider())
    return captured


@pytest.mark.asyncio
async def test_hint_returns_guidance_and_strips_code(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub_provider(
        monkeypatch,
        "Think about the empty string case.\n```python\nreturn 'solution'\n```\nThen check formatting.",
    )

    response = await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
    assert response.status_code == 200
    body = response.json()

    assert "solution'" not in body["text"]
    assert body["filtered"] is True
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_hint_refuses_when_everything_was_filtered(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An all-code reply must produce an error, not an empty panel."""
    _stub_provider(monkeypatch, "```python\ndef greet(name):\n    return name\n```")

    response = await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
    assert response.status_code == 502
    assert "withheld" in response.json()["detail"]


@pytest.mark.asyncio
async def test_hint_rejects_unknown_challenge(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch, "A hint.")
    response = await client.post(HINT, json={"challenge_id": "nope", "code": "x = 1"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_explain_requires_error_text(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch, "An explanation.")
    response = await client.post(
        EXPLAIN, json={"challenge_id": CHALLENGE, "code": "x = 1", "error_text": "   "}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_review_requires_code(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch, "A review.")
    response = await client.post(REVIEW, json={"challenge_id": CHALLENGE, "code": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recommend_uses_the_learners_record(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _stub_provider(monkeypatch, "Focus on testing next.")

    response = await client.post(RECOMMEND, json={})
    assert response.status_code == 200
    assert response.json()["text"] == "Focus on testing next."
    # The prompt must carry real context, not a generic request.
    assert "completed 0 of" in captured[0][-1].content


@pytest.mark.asyncio
async def test_request_bodies_reject_unknown_fields(
    client: AsyncClient, ai_settings: Settings
) -> None:
    response = await client.post(
        HINT, json={"challenge_id": CHALLENGE, "code": "x = 1", "model": "gpt-5"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_oversized_code_is_rejected(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch, "A hint.")
    response = await client.post(
        HINT, json={"challenge_id": CHALLENGE, "code": "x" * 25_000}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_hint_prompt_includes_the_challenge_description(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt must carry the real challenge material, not a generic ask."""
    captured = _stub_provider(monkeypatch, "A hint.")

    await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})

    prompt = captured[0][-1].content
    # The title and the description body from the fixture challenge.
    assert "Hello World" in prompt
    assert "Do the thing." in prompt
    # And the learner's own code.
    assert "x = 1" in prompt


@pytest.mark.asyncio
async def test_ai_status_reflects_enabled_configuration(
    client: AsyncClient, ai_settings: Settings
) -> None:
    body = (await client.get(STATUS)).json()
    assert body["enabled"] is True
    assert body["requests_remaining"] > 0


@pytest.mark.asyncio
async def test_rate_limit_is_enforced(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A runaway client must not be able to burn the AI budget."""
    _stub_provider(monkeypatch, "A hint.")
    ai_settings.ai_requests_per_hour = 3

    for _ in range(3):
        assert (
            await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
        ).status_code == 200

    limited = await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
    assert limited.status_code == 429
    assert "limit" in limited.json()["detail"].lower()


@pytest.mark.asyncio
async def test_status_reports_consumed_quota(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch, "A hint.")
    ai_settings.ai_requests_per_hour = 5

    before = (await client.get(STATUS)).json()["requests_remaining"]
    await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
    after = (await client.get(STATUS)).json()["requests_remaining"]

    assert after == before - 1


@pytest.mark.asyncio
async def test_upstream_failure_is_reported_as_503(
    client: AsyncClient, ai_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provider outage must not surface as a 500 or leak internals."""
    import app.api.ai as ai_module

    class BrokenProvider:
        name = "broken"
        available = True

        async def complete(self, messages, *, max_tokens: int = 700) -> str:
            raise AIUnavailableError("The AI provider could not be reached")

    monkeypatch.setattr(ai_module, "build_provider", lambda _settings: BrokenProvider())

    response = await client.post(HINT, json={"challenge_id": CHALLENGE, "code": "x = 1"})
    assert response.status_code == 503
    assert "example.invalid" not in response.text
    assert "test-key" not in response.text
