"""Challenge catalogue and detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import OptionalUser, RepositoryDep, SessionDep, SettingsDep
from app.models import ChallengeProgress, ProgressStatus, User
from app.schemas import ChallengeDetail, ChallengeSummary

router = APIRouter(prefix="/challenges", tags=["challenges"])


@router.get("", response_model=list[ChallengeSummary], summary="List every challenge")
async def list_challenges(
    session: SessionDep,
    repository: RepositoryDep,
    user: OptionalUser,
    track: str | None = None,
) -> list[ChallengeSummary]:
    """Return the catalogue with the caller's completion state attached.

    Readable while signed out, in which case nothing is marked complete.
    """
    progress = await _progress_map(session, user)

    challenges = repository.all()
    if track:
        challenges = [c for c in challenges if c.track == track]

    return [
        _summary(challenge, progress.get(challenge.id))
        for challenge in challenges
    ]


@router.get(
    "/{challenge_id}",
    response_model=ChallengeDetail,
    summary="Fetch one challenge with starter code and visible tests",
)
async def get_challenge(
    challenge_id: str,
    session: SessionDep,
    repository: RepositoryDep,
    user: OptionalUser,
    settings: SettingsDep,
) -> ChallengeDetail:
    """Return challenge material. Hidden tests are never included."""
    try:
        challenge = repository.get(challenge_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Challenge {challenge_id!r} does not exist",
        ) from exc

    row = await _progress_row(session, user, challenge.id)
    base = _summary(challenge, row)

    return ChallengeDetail(
        **base.model_dump(),
        description=challenge.files.description,
        starter_code=challenge.files.starter,
        entry_file=challenge.entry_file,
        time_limit_ms=challenge.time_limit_ms,
        # Clamped to the platform ceiling so the workspace never advertises
        # more memory than the sandbox will actually grant. All 35 challenges
        # currently declare 128 or 256 MB, so every one of them is clamped here.
        memory_limit_mb=min(challenge.memory_limit_mb, settings.max_memory_limit_mb),
        visible_tests=challenge.files.visible_tests,
        # ``kind`` and ``is_project`` already come from the summary projection.
        # Single-file challenges expose just the entry, so the editor does not
        # render a file tree for something with one file.
        starter_files=challenge.files.starter_files or {challenge.entry_file: challenge.files.starter},
        rubric=challenge.files.rubric,
    )


def _summary(challenge, row: ChallengeProgress | None) -> ChallengeSummary:
    completed = row is not None and row.status is ProgressStatus.COMPLETED
    return ChallengeSummary(
        id=challenge.id,
        title=challenge.title,
        summary=challenge.summary,
        difficulty=challenge.difficulty,
        track=challenge.track,
        module=challenge.module,
        level=challenge.level,
        python_version=challenge.python_version,
        points=challenge.points,
        order_index=challenge.order_index,
        skills=challenge.skills,
        tags=challenge.tags,
        visible_test_count=challenge.visible_test_count,
        skill_mastery=row.best_score if row else 0,
        completed=completed,
        best_score=row.best_score if row else 0,
        kind=challenge.kind,
        is_project=challenge.is_project,
    )


async def _progress_map(session: SessionDep, user: User | None) -> dict[str, ChallengeProgress]:
    """Per-challenge progress for the caller; empty when signed out."""
    if user is None:
        return {}
    rows = (
        await session.scalars(
            select(ChallengeProgress).where(ChallengeProgress.user_id == user.id)
        )
    ).all()
    return {row.challenge_id: row for row in rows}


async def _progress_row(
    session: SessionDep, user: User | None, challenge_id: str
) -> ChallengeProgress | None:
    if user is None:
        return None
    return await session.scalar(
        select(ChallengeProgress).where(
            ChallengeProgress.user_id == user.id,
            ChallengeProgress.challenge_id == challenge_id,
        )
    )
