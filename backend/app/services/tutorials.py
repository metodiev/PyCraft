"""Loads tutorials from disk and validates their structure.

Tutorials are reading material that sits *beside* the challenge catalogue: they
give a learner the concepts before a challenge asks them to apply those
concepts. They are deliberately not graded — completion in PyCraft is earned by
passing tests — so a tutorial has no starter file, no tests and no points.

Like challenges, they are authored as files so they can be reviewed in pull
requests. This module is the only place that knows the on-disk layout, which
keeps the format swappable without touching the API layer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

METADATA_FILE = "metadata.json"
CONTENT_FILE = "tutorial.md"

# Fields a tutorial must define; anything else is optional with a default.
REQUIRED_FIELDS = ("id", "title", "track")
MAX_ID_LENGTH = 120
MAX_TITLE_LENGTH = 200
MAX_SUMMARY_LENGTH = 400

# Tracks a tutorial may belong to. Kept in step with the roadmap and the
# authoring service so a tutorial cannot reference a track that does not exist.
ALLOWED_TRACKS = (
    "python-fundamentals",
    "python-professional",
    "testing-quality",
    "web-development",
    "databases",
    "async-concurrency",
    "backend-engineering",
    "performance",
    "cloud-devops",
    "distributed-systems",
    "system-design",
    "software-architecture",
    "principal-engineer",
)

DIFFICULTIES = ("beginner", "easy", "intermediate", "advanced", "expert")


class TutorialFormatError(ValueError):
    """Raised when a tutorial on disk is malformed."""


class TutorialNotFoundError(LookupError):
    """Raised when a requested tutorial does not exist."""


@dataclass(slots=True)
class LoadedTutorial:
    """A fully materialised tutorial: metadata plus its article body."""

    id: str
    title: str
    summary: str
    track: str
    difficulty: str
    level: str
    order_index: int
    reading_minutes: int
    tags: list[str]
    skills: list[str]
    content: str
    path: Path
    # Optional link to a challenge that applies this tutorial's material.
    related_challenge: str | None = None

    @property
    def word_count(self) -> int:
        return len(self.content.split())


@dataclass(slots=True)
class TutorialReadState:
    """A tutorial as seen by one reader."""

    tutorial: LoadedTutorial
    read: bool = False
    progress_pct: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class TutorialRepository:
    """Reads and caches tutorials from a content directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._cache: dict[str, LoadedTutorial] = {}
        self._errors: list[str] = []

    # --- discovery -------------------------------------------------------
    def _discover_paths(self) -> list[Path]:
        if not self._root.exists():
            logger.warning("Tutorials directory %s does not exist", self._root)
            return []
        return sorted(p.parent for p in self._root.glob(f"*/*/{METADATA_FILE}"))

    def load_all(self, *, strict: bool = False) -> list[LoadedTutorial]:
        """Load every valid tutorial; optionally fail fast on bad content."""
        loaded: list[LoadedTutorial] = []
        self._errors = []
        for path in self._discover_paths():
            try:
                tutorial = self._load_one(path)
            except TutorialFormatError as exc:
                if strict:
                    raise
                self._errors.append(f"{path}: {exc}")
                logger.error("Skipping invalid tutorial at %s: %s", path, exc)
                continue
            except (OSError, json.JSONDecodeError) as exc:
                if strict:
                    raise TutorialFormatError(f"{path}: {exc}") from exc
                self._errors.append(f"{path}: {exc}")
                logger.error("Failed to read tutorial at %s: %s", path, exc)
                continue
            loaded.append(tutorial)

        # ``id`` must equal ``<track>-<slug>`` and directories are unique, so a
        # duplicate id cannot occur here; no separate uniqueness pass is needed.
        self._cache = {t.id: t for t in loaded}
        loaded.sort(key=lambda t: (t.track, t.order_index, t.id))
        return loaded

    @property
    def errors(self) -> list[str]:
        """Human-readable problems found during the last :meth:`load_all`."""
        return list(self._errors)

    # --- access ----------------------------------------------------------
    def get(self, tutorial_id: str) -> LoadedTutorial:
        try:
            return self._cache[tutorial_id]
        except KeyError as exc:
            raise TutorialNotFoundError(tutorial_id) from exc

    def all(self) -> list[LoadedTutorial]:
        return sorted(self._cache.values(), key=lambda t: (t.track, t.order_index, t.id))

    def by_track(self, track: str) -> list[LoadedTutorial]:
        return [t for t in self.all() if t.track == track]

    def ids(self) -> list[str]:
        return [t.id for t in self.all()]

    @property
    def total_reading_minutes(self) -> int:
        return sum(t.reading_minutes for t in self.all())

    # --- loading ---------------------------------------------------------
    def _load_one(self, path: Path) -> LoadedTutorial:
        raw = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise TutorialFormatError("metadata.json must contain a JSON object")

        for name in REQUIRED_FIELDS:
            if not raw.get(name):
                raise TutorialFormatError(f"metadata.json is missing required field {name!r}")

        tutorial_id = str(raw["id"])
        if len(tutorial_id) > MAX_ID_LENGTH:
            raise TutorialFormatError(f"id exceeds {MAX_ID_LENGTH} characters")

        track = str(raw["track"])
        if track not in ALLOWED_TRACKS:
            raise TutorialFormatError(
                f"unknown track {track!r}; valid tracks: {', '.join(ALLOWED_TRACKS)}"
            )
        if path.parent.name != track:
            raise TutorialFormatError(
                f"track {track!r} does not match directory {path.parent.name!r}"
            )
        expected_slug = _slug(tutorial_id, track)
        if path.name != expected_slug:
            raise TutorialFormatError(
                f"id {tutorial_id!r} does not match directory name {path.name!r}"
            )

        title = str(raw["title"]).strip()
        if len(title) > MAX_TITLE_LENGTH:
            raise TutorialFormatError(f"title exceeds {MAX_TITLE_LENGTH} characters")

        difficulty = str(raw.get("difficulty", "beginner")).lower()
        if difficulty not in DIFFICULTIES:
            raise TutorialFormatError(
                f"difficulty must be one of {', '.join(DIFFICULTIES)}, got {difficulty!r}"
            )

        content_path = path / CONTENT_FILE
        if not content_path.is_file():
            raise TutorialFormatError(f"missing {CONTENT_FILE}")
        content = content_path.read_text(encoding="utf-8")
        if not content.strip():
            raise TutorialFormatError(f"{CONTENT_FILE} is empty")

        related = raw.get("related_challenge")
        related_challenge = str(related).strip() if related else None

        return LoadedTutorial(
            id=tutorial_id,
            title=title,
            summary=str(raw.get("summary", ""))[:MAX_SUMMARY_LENGTH],
            track=track,
            difficulty=difficulty,
            level=str(raw.get("level", "junior")),
            order_index=int(raw.get("order_index", 0)),
            reading_minutes=int(raw.get("reading_minutes", 0) or _estimate_minutes(content)),
            tags=_string_list(raw.get("tags")),
            skills=_string_list(raw.get("skills")),
            content=content,
            path=path,
            related_challenge=related_challenge,
        )


def _slug(tutorial_id: str, track: str) -> str:
    return tutorial_id[len(track) + 1 :] if tutorial_id.startswith(f"{track}-") else tutorial_id


def _estimate_minutes(content: str) -> int:
    """Reading time when an author does not state one.

    A developer reading technical prose with code samples covers roughly 200
    words a minute, and the floor of 1 keeps a stub from claiming zero.
    """
    return max(1, round(len(content.split()) / 200))


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []
