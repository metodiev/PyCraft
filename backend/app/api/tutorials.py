"""Tutorial catalogue and reading endpoints.

Tutorials are reading material that prepares a learner for the challenges. They
are intentionally ungraded: no XP, no points, no effect on level. The only
per-user state is a self-reported "read" marker, which exists so a learner can
see what they have covered and pick up where they left off.

The catalogue and an article body stay readable while signed out, matching the
challenge catalogue, so a visitor can evaluate the material before signing up.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import select

from app.api.deps import CurrentUser, OptionalUser, SessionDep, TutorialRepoDep
from app.db.base import utcnow
from app.models import TutorialRead, User
from app.schemas import (
    TutorialCatalogue,
    TutorialDetail,
    TutorialReadResponse,
    TutorialSummary,
    TutorialTrack,
)
from app.services.roadmap import STAGES_BY_ID
from app.services.tutorials import LoadedTutorial, TutorialNotFoundError

router = APIRouter(prefix="/tutorials", tags=["tutorials"])


@router.get("", response_model=TutorialCatalogue, summary="List every tutorial")
async def list_tutorials(
    session: SessionDep,
    repository: TutorialRepoDep,
    user: OptionalUser,
) -> TutorialCatalogue:
    """Return the catalogue grouped by track, with the caller's read state.

    Readable while signed out, in which case nothing is marked read.
    """
    reads = await _read_ids(session, user)
    tutorials = repository.all()

    grouped: dict[str, list[TutorialSummary]] = {}
    for tutorial in tutorials:
        grouped.setdefault(tutorial.track, []).append(_summary(tutorial, reads))

    tracks = [
        TutorialTrack(
            track=track,
            label=_track_label(track),
            tutorials=entries,
            read_count=sum(1 for entry in entries if entry.read),
            total=len(entries),
        )
        for track, entries in grouped.items()
    ]

    return TutorialCatalogue(
        tracks=tracks,
        total=len(tutorials),
        read_count=sum(1 for tutorial in tutorials if tutorial.id in reads),
        reading_minutes=repository.total_reading_minutes,
    )


@router.get(
    "/{tutorial_id}",
    response_model=TutorialDetail,
    summary="Fetch one tutorial with its article body",
)
async def get_tutorial(
    tutorial_id: str,
    session: SessionDep,
    repository: TutorialRepoDep,
    user: OptionalUser,
) -> TutorialDetail:
    """Return a tutorial and its Markdown body."""
    tutorial = _require(repository, tutorial_id)
    reads = await _read_ids(session, user)
    base = _summary(tutorial, reads)
    return TutorialDetail(**base.model_dump(), content=tutorial.content)


@router.post(
    "/{tutorial_id}/read",
    response_model=TutorialReadResponse,
    summary="Mark a tutorial as read",
)
async def mark_read(
    tutorial_id: str,
    session: SessionDep,
    repository: TutorialRepoDep,
    user: CurrentUser,
) -> TutorialReadResponse:
    """Record that the learner has read this tutorial.

    Idempotent: re-reading an already-read tutorial leaves the original
    timestamp alone, so the marker reflects when it was genuinely completed.
    """
    _require(repository, tutorial_id)
    row = await session.scalar(
        select(TutorialRead).where(
            TutorialRead.user_id == user.id,
            TutorialRead.tutorial_id == tutorial_id,
        )
    )
    if row is None:
        session.add(TutorialRead(user_id=user.id, tutorial_id=tutorial_id, read_at=utcnow()))
    elif row.read_at is None:
        row.read_at = utcnow()
    await session.commit()
    return TutorialReadResponse(tutorial_id=tutorial_id, read=True)


@router.delete(
    "/{tutorial_id}/read",
    response_model=TutorialReadResponse,
    summary="Clear a tutorial's read marker",
)
async def clear_read(
    tutorial_id: str,
    session: SessionDep,
    repository: TutorialRepoDep,
    user: CurrentUser,
) -> TutorialReadResponse:
    """Undo the read marker, so a learner can reset their own coverage."""
    _require(repository, tutorial_id)
    await session.execute(
        sql_delete(TutorialRead).where(
            TutorialRead.user_id == user.id,
            TutorialRead.tutorial_id == tutorial_id,
        )
    )
    await session.commit()
    return TutorialReadResponse(tutorial_id=tutorial_id, read=False)


# --- helpers -------------------------------------------------------------
def _require(repository: TutorialRepoDep, tutorial_id: str) -> LoadedTutorial:
    try:
        return repository.get(tutorial_id)
    except TutorialNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tutorial {tutorial_id!r} does not exist",
        ) from exc


async def _read_ids(session: SessionDep, user: User | None) -> set[str]:
    """Ids the caller has marked read; empty when signed out."""
    if user is None:
        return set()
    rows = await session.scalars(
        select(TutorialRead.tutorial_id).where(
            TutorialRead.user_id == user.id,
            TutorialRead.read_at.is_not(None),
        )
    )
    return set(rows.all())


def _summary(tutorial: LoadedTutorial, reads: set[str]) -> TutorialSummary:
    return TutorialSummary(
        id=tutorial.id,
        title=tutorial.title,
        summary=tutorial.summary,
        track=tutorial.track,
        difficulty=tutorial.difficulty,
        level=tutorial.level,
        order_index=tutorial.order_index,
        reading_minutes=tutorial.reading_minutes,
        tags=tutorial.tags,
        skills=tutorial.skills,
        word_count=tutorial.word_count,
        related_challenge=tutorial.related_challenge,
        read=tutorial.id in reads,
    )


def _track_label(track: str) -> str:
    """Human label for a track, reusing the roadmap's wording.

    The two sections describe the same stages, so sharing the roadmap titles
    keeps "Python Fundamentals" meaning the same thing on both pages.
    """
    stage = STAGES_BY_ID.get(track)
    return stage.title if stage is not None else track.replace("-", " ").title()
