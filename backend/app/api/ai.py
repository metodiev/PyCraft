"""AI assistance endpoints.

Every endpoint is opt-in, rate limited per user, and returns guidance rather
than solutions. The response always states whether the text was filtered, so the
UI can be honest about what happened.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, RepositoryDep, SessionDep, SettingsDep
from app.models import ProgressStatus, SkillProgress
from app.services.ai import (
    AIRateLimitedError,
    AIUnavailableError,
    build_provider,
    explanation_messages,
    hint_messages,
    recommendation_messages,
    review_messages,
    sanitise,
)
from app.services.roadmap import SKILL_LABELS, level_for_xp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatus(BaseModel):
    enabled: bool
    provider: str
    requests_remaining: int


class AIText(BaseModel):
    """Generated guidance.

    ``filtered`` is true when a code block or whole-solution phrasing was
    removed, so the UI can explain why output may look truncated.
    """

    text: str
    filtered: bool = False
    provider: str = ""


class HintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str
    code: str = Field(default="", max_length=20_000)
    attempt_number: int = Field(default=1, ge=1, le=20)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str
    code: str = Field(default="", max_length=20_000)
    error_text: str = Field(default="", max_length=10_000)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: str
    code: str = Field(default="", max_length=20_000)


# In-process sliding window, keyed by user. Deliberately simple: a multi-worker
# deployment would need Redis here, which is the same upgrade path the job queue
# takes. Correctness under a single worker is exact.
_request_log: dict[str, deque[float]] = defaultdict(deque)


def _check_rate_limit(user_id: str, limit: int) -> int:
    """Consume one request, returning how many remain. Raises 429 when exhausted."""
    if limit <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="AI assistance is disabled by the current rate limit",
        )

    now = time.monotonic()
    window = _request_log[user_id]
    while window and now - window[0] > 3600:
        window.popleft()

    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You have reached the AI request limit ({limit} per hour). Try again later.",
        )

    window.append(now)
    return limit - len(window)


def _remaining(user_id: str, limit: int) -> int:
    now = time.monotonic()
    window = _request_log[user_id]
    while window and now - window[0] > 3600:
        window.popleft()
    return max(0, limit - len(window))


async def _generate(messages, settings) -> AIText:
    """Run a prompt and sanitise the result."""
    provider = build_provider(settings)
    try:
        raw = await provider.complete(messages, max_tokens=settings.ai_max_tokens)
    except AIUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except AIRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc

    text, filtered = sanitise(raw)
    if not text:
        # A fully filtered response is worse than none: say so rather than
        # showing an empty panel.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI response was withheld because it contained a direct solution. Try again.",
        )
    return AIText(text=text, filtered=filtered, provider=provider.name)


def _require_enabled(settings: SettingsDep) -> None:
    if not settings.ai_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "AI assistance is not enabled on this deployment. "
                "Set PYCRAFT_AI_PROVIDER and PYCRAFT_AI_API_KEY to enable it."
            ),
        )


@router.get("/status", response_model=AIStatus, summary="Is AI assistance available?")
async def ai_status(user: CurrentUser, settings: SettingsDep) -> AIStatus:
    provider = build_provider(settings)
    return AIStatus(
        enabled=settings.ai_enabled,
        provider=provider.name,
        requests_remaining=_remaining(str(user.id), settings.ai_requests_per_hour),
    )


@router.post("/hint", response_model=AIText, summary="Get a hint for a challenge")
async def get_hint(
    payload: HintRequest,
    user: CurrentUser,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> AIText:
    """Nudge the learner towards the next step.

    Grounded in the author's own hints, so generated guidance stays consistent
    with the intended difficulty instead of inventing a shortcut.
    """
    _require_enabled(settings)
    _check_rate_limit(str(user.id), settings.ai_requests_per_hour)

    try:
        challenge = repository.get(payload.challenge_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc

    # The author's hints live in the description as <details> blocks; extract
    # their bodies so the model can build on them.
    authored_hints = _extract_hints(challenge.files.description)

    return await _generate(
        hint_messages(
            challenge_title=challenge.title,
            description=challenge.files.description,
            code=payload.code,
            authored_hints=authored_hints,
            attempt_number=payload.attempt_number,
        ),
        settings,
    )


@router.post("/explain", response_model=AIText, summary="Explain an error")
async def explain_error(
    payload: ExplainRequest,
    user: CurrentUser,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> AIText:
    """Explain what went wrong, without supplying the fix."""
    _require_enabled(settings)
    _check_rate_limit(str(user.id), settings.ai_requests_per_hour)

    try:
        challenge = repository.get(payload.challenge_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc

    if not payload.error_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide the error output to explain",
        )

    return await _generate(
        explanation_messages(
            challenge_title=challenge.title,
            error_text=payload.error_text,
            code=payload.code,
        ),
        settings,
    )


@router.post("/review", response_model=AIText, summary="Review a solution")
async def review_solution(
    payload: ReviewRequest,
    user: CurrentUser,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> AIText:
    """Senior-engineer style review of readability, naming and edge cases."""
    _require_enabled(settings)
    _check_rate_limit(str(user.id), settings.ai_requests_per_hour)

    try:
        challenge = repository.get(payload.challenge_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown challenge") from exc

    if not payload.code.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No code to review"
        )

    return await _generate(
        review_messages(challenge_title=challenge.title, code=payload.code),
        settings,
    )


@router.post("/recommend", response_model=AIText, summary="What to work on next")
async def recommend(
    user: CurrentUser,
    session: SessionDep,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> AIText:
    """Recommend a focus area from the learner's actual record."""
    _require_enabled(settings)
    _check_rate_limit(str(user.id), settings.ai_requests_per_hour)

    from app.models import ChallengeProgress

    progress_rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    completed = sum(1 for row in progress_rows if row.status is ProgressStatus.COMPLETED)

    skills = (
        await session.scalars(
            select(SkillProgress).where(SkillProgress.user_id == user.id)
        )
    ).all()
    # Lowest mastery first — those are the real gaps.
    weak = [
        SKILL_LABELS.get(row.skill, row.skill)
        for row in sorted(skills, key=lambda s: s.mastery)[:3]
        if row.mastery < 70
    ]

    recent_titles: list[str] = []
    for row in progress_rows:
        if row.status is not ProgressStatus.COMPLETED:
            continue
        try:
            recent_titles.append(repository.get(row.challenge_id).title)
        except Exception:
            # A challenge can be removed from disk while progress rows remain.
            continue
    recent_titles = recent_titles[-5:]

    return await _generate(
        recommendation_messages(
            level_label=level_for_xp(user.xp)[1],
            completed=completed,
            total=len(repository.all()),
            weak_skills=weak,
            recent_titles=recent_titles,
        ),
        settings,
    )


def _extract_hints(description: str) -> list[str]:
    """Pull the bodies of ``<details>`` hint blocks out of a description."""
    hints: list[str] = []
    for match in re.finditer(
        r"<details>\s*<summary>(?P<title>.*?)</summary>(?P<body>.*?)</details>",
        description,
        re.DOTALL | re.IGNORECASE,
    ):
        body = re.sub(r"<[^>]+>", "", match.group("body")).strip()
        if body:
            hints.append(body[:600])
    return hints[:5]
