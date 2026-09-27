"""AI assistance.

The spec is explicit: **AI must not become the primary learning mechanism.**
Every provider here is a *scaffold*, never a solution generator. That constraint
is enforced structurally, not just by prompting:

* The catalogue exposes no "write my code" capability at all.
* Hint prompts are built from the challenge's own authored hints, so the model
  elaborates on curated material instead of inventing a walkthrough.
* Review prompts receive the learner's code but are instructed to report
  observations, and responses are filtered for fenced code blocks.
* A provider may be ``NullProvider`` (the default), and every endpoint fails
  with a clear message rather than silently degrading.

Pluggable by design: ``AIProvider`` is a two-method protocol, so swapping in
OpenAI, Anthropic, or a self-hosted model touches one class.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


class AIUnavailableError(Exception):
    """Raised when no AI provider is configured."""


class AIRateLimitedError(Exception):
    """Raised when the provider is rate limiting or over quota."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


class AIProvider(Protocol):
    """Minimal async chat interface.

    Deliberately small: the platform needs plain text completions, not tools,
    streaming or function calling.
    """

    name: str
    available: bool

    async def complete(self, messages: list[ChatMessage], *, max_tokens: int = 700) -> str: ...


# --- no-op provider ------------------------------------------------------
class NullProvider:
    """Default provider. Reports unavailability so endpoints fail loudly."""

    name = "disabled"
    available = False

    async def complete(self, messages: list[ChatMessage], *, max_tokens: int = 700) -> str:
        raise AIUnavailableError(
            "AI assistance is not configured on this deployment. "
            "Set PYCRAFT_AI_PROVIDER to enable it."
        )


# --- HTTP providers ------------------------------------------------------
class OpenAICompatibleProvider:
    """Any OpenAI-compatible ``/chat/completions`` endpoint.

    Works with OpenAI, Azure OpenAI, Together, Groq, vLLM, Ollama and others,
    which is why this one provider covers most self-hosting choices.
    """

    name = "openai"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.ai_base_url.rstrip("/")
        self._api_key = settings.ai_api_key
        self._model = settings.ai_model

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._base_url and self._model)

    async def complete(self, messages: list[ChatMessage], *, max_tokens: int = 700) -> str:
        if not self.available:
            raise AIUnavailableError("AI provider is not fully configured")

        import httpx

        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": self._settings.ai_temperature,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        url = f"{self._base_url}/chat/completions"

        try:
            async with httpx.AsyncClient(timeout=self._settings.ai_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            # Never surface an upstream URL or credential in the error.
            logger.warning("AI provider request failed: %s", type(exc).__name__)
            raise AIUnavailableError("The AI provider could not be reached") from exc

        if response.status_code == 429:
            raise AIRateLimitedError("The AI provider is rate limiting requests. Try again shortly.")
        if response.status_code >= 400:
            logger.warning("AI provider returned %s", response.status_code)
            raise AIUnavailableError("The AI provider rejected the request")

        try:
            body = response.json()
            return str(body["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("Unexpected AI provider response shape")
            raise AIUnavailableError("The AI provider returned an unexpected response") from exc


def build_provider(settings: Settings) -> AIProvider:
    """Construct the configured provider."""
    if settings.ai_provider == "openai":
        return OpenAICompatibleProvider(settings)
    return NullProvider()


# --- solution-leak filtering ---------------------------------------------
_FENCED_CODE = re.compile(r"```")
# Phrases that indicate the model is handing over a complete answer.
_SOLUTION_PHRASES = (
    "here is the complete solution",
    "here's the complete solution",
    "here is the full solution",
    "here's the full solution",
    "the complete implementation is",
    "copy and paste this",
)


def sanitise(text: str) -> tuple[str, bool]:
    """Strip code blocks and whole-solution phrasing.

    Returns ``(text, was_filtered)``. The prompt already forbids solutions; this
    makes the constraint enforceable rather than merely requested, because a
    model can always ignore an instruction.
    """
    if not text:
        return "", False

    filtered = False
    lowered = text.lower()
    if any(phrase in lowered for phrase in _SOLUTION_PHRASES):
        filtered = True

    # Drop fenced code blocks entirely. Inline `code` spans are kept: they are
    # how hints legitimately reference a function or a value.
    if _FENCED_CODE.search(text):
        parts: list[str] = []
        in_block = False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_block = not in_block
                continue
            if not in_block:
                parts.append(line)
        text = "\n".join(parts).strip()
        filtered = True

    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, filtered


# --- prompt construction -------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior Python engineer mentoring a learner on PyCraft, an "
    "interactive training platform.\n\n"
    "Absolute rules:\n"
    "1. NEVER write a complete solution, complete function body, or code the "
    "learner can paste in and submit. This is the most important rule.\n"
    "2. Never include fenced code blocks. Refer to identifiers inline instead.\n"
    "3. Ask guiding questions and describe approaches, so the learner writes "
    "the code themselves.\n"
    "4. Be concise and specific. No filler, no praise padding.\n"
    "5. If the learner asks you to write the answer, decline and offer the next "
    "conceptual step instead."
)


def hint_messages(
    *,
    challenge_title: str,
    description: str,
    code: str,
    authored_hints: list[str],
    attempt_number: int,
) -> list[ChatMessage]:
    """Build a hint request grounded in the author's own hints.

    Passing the authored hints keeps generated guidance consistent with the
    challenge's intended difficulty, and gives the model concrete material so it
    does not have to invent a path.
    """
    hints_block = (
        "\n".join(f"- {hint}" for hint in authored_hints) if authored_hints else "(none authored)"
    )
    depth = "a gentle nudge towards the right area" if attempt_number <= 1 else "a more concrete next step"

    return [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage(
            "user",
            f"Challenge: {challenge_title}\n\n"
            f"Description:\n{description[:4000]}\n\n"
            f"The challenge author provides these hints:\n{hints_block}\n\n"
            f"The learner has attempted this {attempt_number} time(s). "
            f"Current code:\n{code[:4000]}\n\n"
            f"Give {depth}. At most 3 short sentences, and no code blocks. "
            "Point at what to think about, not what to type.",
        ),
    ]


def explanation_messages(
    *, challenge_title: str, error_text: str, code: str
) -> list[ChatMessage]:
    """Explain an error without fixing it."""
    return [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage(
            "user",
            f"Challenge: {challenge_title}\n\n"
            f"The learner's code produced this error or failure:\n{error_text[:3000]}\n\n"
            f"Their code:\n{code[:4000]}\n\n"
            "Explain what is going wrong and why, in plain language a learner can "
            "act on. Do not provide corrected code. At most 4 short sentences.",
        ),
    ]


def review_messages(*, challenge_title: str, code: str) -> list[ChatMessage]:
    """Review code quality, not correctness."""
    return [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage(
            "user",
            f"Challenge: {challenge_title}\n\n"
            f"Review this solution as a code reviewer would:\n{code[:6000]}\n\n"
            "Comment on readability, naming, structure and edge cases — the things "
            "a senior engineer would raise in review. Do not rewrite the code. "
            "Give at most 4 specific observations, most important first.",
        ),
    ]


def recommendation_messages(
    *, level_label: str, completed: int, total: int, weak_skills: list[str], recent_titles: list[str]
) -> list[ChatMessage]:
    """Suggest what to work on next, from the learner's actual record."""
    weak = ", ".join(weak_skills) if weak_skills else "none identified yet"
    recent = ", ".join(recent_titles) if recent_titles else "nothing yet"

    return [
        ChatMessage("system", SYSTEM_PROMPT),
        ChatMessage(
            "user",
            f"A learner on PyCraft is at level {level_label}, and has completed "
            f"{completed} of {total} challenges.\n\n"
            f"Recently solved: {recent}\n"
            f"Skills needing work: {weak}\n\n"
            "Recommend what to focus on next and why, in 2-3 sentences. Be "
            "specific about the skill, not the challenge title.",
        ),
    ]


__all__ = [
    "AIProvider",
    "AIRateLimitedError",
    "AIUnavailableError",
    "ChatMessage",
    "NullProvider",
    "OpenAICompatibleProvider",
    "build_provider",
    "explanation_messages",
    "hint_messages",
    "recommendation_messages",
    "review_messages",
    "sanitise",
]
