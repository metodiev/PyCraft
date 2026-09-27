"""Challenge authoring endpoints (author/admin only).

Publishing writes real files into the content directory, so it is restricted and
validated. A draft is checked in full before anything touches disk, and the
write is staged so a failure cannot leave a malformed challenge behind.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, RepositoryDep, RequireAuthor, SettingsDep
from app.models.roles import UserRole
from app.services.authoring import (
    ALLOWED_TRACKS,
    AuthoringError,
    ValidationIssue,
    blocking_issues,
    draft_from_payload,
    load_draft,
    publish_draft,
    refresh_catalogue,
    validate_draft,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/authoring", tags=["authoring"])


class DraftPayload(BaseModel):
    """An authored challenge. Unknown fields are rejected so a typo is caught."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(default="", max_length=80)
    track: str = ""
    title: str = Field(default="", max_length=200)
    summary: str = Field(default="", max_length=500)
    difficulty: str = "beginner"
    level: str = "junior"
    module: str = Field(default="General", max_length=80)
    points: int = 50
    order_index: int = 1
    time_limit_ms: int = 5_000
    memory_limit_mb: int = 128
    python_version: str = "3.12"
    skills: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=20)
    description: str = ""
    starter_code: str = ""
    visible_tests: dict[str, str] = Field(default_factory=dict)
    hidden_tests: dict[str, str] = Field(default_factory=dict)


class IssueOut(BaseModel):
    field: str
    message: str
    severity: str


class ValidationOut(BaseModel):
    valid: bool
    issues: list[IssueOut]
    error_count: int
    warning_count: int


class TrackOption(BaseModel):
    id: str
    label: str


@router.get("/tracks", response_model=list[TrackOption], summary="Available tracks")
async def list_tracks(user: RequireAuthor) -> list[TrackOption]:
    """Tracks an author may publish into."""
    return [
        TrackOption(
            id=track,
            label=track.replace("-", " ").title(),
        )
        for track in ALLOWED_TRACKS
    ]


@router.post("/validate", response_model=ValidationOut, summary="Validate a draft")
async def validate(payload: DraftPayload, user: RequireAuthor) -> ValidationOut:
    """Check a draft without saving it.

    Returns *all* problems at once so the editor can highlight them together,
    rather than making the author fix them one at a time.
    """
    try:
        draft = draft_from_payload(payload.model_dump())
    except AuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    issues = validate_draft(draft)
    return _to_validation(issues)


@router.post("/publish", response_model=ValidationOut, summary="Publish a challenge")
async def publish(
    payload: DraftPayload,
    user: RequireAuthor,
    repository: RepositoryDep,
    settings: SettingsDep,
) -> ValidationOut:
    """Validate and write a challenge into the content directory.

    On validation failure nothing is written and the issues are returned, so the
    author can see exactly what to fix.
    """
    try:
        draft = draft_from_payload(payload.model_dump())
    except AuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    issues = validate_draft(draft)
    if blocking_issues(issues):
        return _to_validation(issues)

    try:
        publish_draft(draft, settings.challenges_dir)
    except AuthoringError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except OSError as exc:
        logger.exception("Failed to publish challenge %s", draft.challenge_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not write the challenge to disk: {exc}",
        ) from exc

    # Make the new challenge available without a restart.
    refresh_catalogue(repository)
    logger.info("Author %s published %s", user.email, draft.challenge_id)

    return _to_validation(issues)


@router.get(
    "/challenges/{track}/{slug}",
    response_model=DraftPayload,
    summary="Load a challenge for editing",
)
async def get_draft(track: str, slug: str, user: RequireAuthor, settings: SettingsDep) -> DraftPayload:
    draft = load_draft(settings.challenges_dir, track, slug)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Challenge not found")

    return DraftPayload(
        slug=draft.slug,
        track=draft.track,
        title=draft.title,
        summary=draft.summary,
        difficulty=draft.difficulty,
        level=draft.level,
        module=draft.module,
        points=draft.points,
        order_index=draft.order_index,
        time_limit_ms=draft.time_limit_ms,
        memory_limit_mb=draft.memory_limit_mb,
        python_version=draft.python_version,
        skills=draft.skills,
        tags=draft.tags,
        description=draft.description,
        starter_code=draft.starter_code,
        visible_tests=draft.visible_tests,
        hidden_tests=draft.hidden_tests,
    )


@router.get("/catalogue", summary="Authoring overview")
async def catalogue_overview(user: RequireAuthor, repository: RepositoryDep) -> dict[str, object]:
    """Every challenge with the counts an author cares about."""
    challenges = repository.all()
    by_track: dict[str, int] = {}
    for challenge in challenges:
        by_track[challenge.track] = by_track.get(challenge.track, 0) + 1

    return {
        "total": len(challenges),
        "by_track": by_track,
        "empty_tracks": [track for track in ALLOWED_TRACKS if track not in by_track],
        "load_errors": repository.errors,
        "challenges": [
            {
                "id": challenge.id,
                "title": challenge.title,
                "track": challenge.track,
                "difficulty": challenge.difficulty,
                "visible_tests": challenge.visible_test_count,
                "hidden_tests": challenge.hidden_test_count,
                "points": challenge.points,
            }
            for challenge in challenges
        ],
    }


@router.get("/access", summary="Whether the caller may author")
async def access(user: CurrentUser) -> dict[str, object]:
    """Lets the frontend decide whether to show the authoring UI."""
    return {
        "can_author": user.role.at_least(UserRole.AUTHOR),
        "role": str(user.role),
    }


def _to_validation(issues: list[ValidationIssue]) -> ValidationOut:
    return ValidationOut(
        valid=not blocking_issues(issues),
        issues=[
            IssueOut(field=issue.field, message=issue.message, severity=issue.severity)
            for issue in issues
        ],
        error_count=len(blocking_issues(issues)),
        warning_count=len([i for i in issues if i.severity == "warning"]),
    )


__all__ = ["router"]
