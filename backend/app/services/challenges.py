"""Loads challenges from disk and validates their structure.

Challenges are authored as files so they can be reviewed in pull requests, then
indexed into the database for querying. This module is the only place that knows
the on-disk layout, which keeps the format swappable (e.g. to an object store or
a CMS) without touching the API layer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

METADATA_FILE = "metadata.json"
DESCRIPTION_FILE = "description.md"
STARTER_DIR = "starter"
TESTS_DIR = "tests"
HIDDEN_PREFIX = "hidden"

# Fields a challenge must define; anything else is optional with a default.
REQUIRED_FIELDS = ("id", "title", "track", "difficulty")
MAX_ID_LENGTH = 120


class ChallengeFormatError(ValueError):
    """Raised when a challenge on disk is malformed."""


class ChallengeNotFoundError(LookupError):
    """Raised when a requested challenge does not exist."""


@dataclass(slots=True)
class ChallengeFiles:
    """Loaded challenge material."""

    description: str
    starter: str
    visible_tests: dict[str, str] = field(default_factory=dict)
    hidden_tests: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LoadedChallenge:
    """A fully materialised challenge: metadata plus its files."""

    id: str
    title: str
    summary: str
    difficulty: str
    track: str
    module: str
    level: str
    python_version: str
    time_limit_ms: int
    memory_limit_mb: int
    points: int
    order_index: int
    skills: list[str]
    entry_file: str
    tags: list[str]
    path: Path
    files: ChallengeFiles

    @property
    def visible_test_count(self) -> int:
        return len(self.files.visible_tests)

    @property
    def hidden_test_count(self) -> int:
        return len(self.files.hidden_tests)


class ChallengeRepository:
    """Reads and caches challenges from a content directory."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._cache: dict[str, LoadedChallenge] = {}
        self._errors: list[str] = []

    # --- discovery -------------------------------------------------------
    def _discover_paths(self) -> list[Path]:
        if not self._root.exists():
            logger.warning("Challenges directory %s does not exist", self._root)
            return []
        paths = sorted(p.parent for p in self._root.glob(f"*/*/{METADATA_FILE}"))
        return paths

    def load_all(self, *, strict: bool = False) -> list[LoadedChallenge]:
        """Load every valid challenge; optionally fail fast on bad content."""
        loaded: list[LoadedChallenge] = []
        self._errors = []
        for path in self._discover_paths():
            try:
                challenge = self._load_one(path)
            except ChallengeFormatError as exc:
                if strict:
                    raise
                self._errors.append(f"{path}: {exc}")
                logger.error("Skipping invalid challenge at %s: %s", path, exc)
                continue
            except (OSError, json.JSONDecodeError) as exc:
                if strict:
                    raise ChallengeFormatError(f"{path}: {exc}") from exc
                self._errors.append(f"{path}: {exc}")
                logger.error("Failed to read challenge at %s: %s", path, exc)
                continue
            loaded.append(challenge)

        # ``id`` must equal ``<track>-<slug>`` and directories are unique, so a
        # duplicate id cannot occur here; no separate uniqueness pass is needed.
        self._cache = {c.id: c for c in loaded}
        loaded.sort(key=lambda c: (c.track, c.order_index, c.id))
        return loaded

    @property
    def errors(self) -> list[str]:
        """Human-readable problems found during the last :meth:`load_all`."""
        return list(self._errors)

    # --- access ----------------------------------------------------------
    def get(self, challenge_id: str) -> LoadedChallenge:
        try:
            return self._cache[challenge_id]
        except KeyError as exc:
            raise ChallengeNotFoundError(challenge_id) from exc

    def all(self) -> list[LoadedChallenge]:
        return sorted(self._cache.values(), key=lambda c: (c.track, c.order_index, c.id))

    def slugs(self) -> list[str]:
        return [c.id for c in self.all()]

    # --- loading ---------------------------------------------------------
    def _load_one(self, path: Path) -> LoadedChallenge:
        raw = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ChallengeFormatError("metadata.json must contain a JSON object")

        for name in REQUIRED_FIELDS:
            if not raw.get(name):
                raise ChallengeFormatError(f"metadata.json is missing required field {name!r}")

        challenge_id = str(raw["id"])
        if len(challenge_id) > MAX_ID_LENGTH:
            raise ChallengeFormatError(f"id exceeds {MAX_ID_LENGTH} characters")
        if path.parent.name != raw["track"]:
            raise ChallengeFormatError(
                f"track {raw['track']!r} does not match directory {path.parent.name!r}"
            )
        if path.name != _slug(challenge_id, str(raw["track"])):
            raise ChallengeFormatError(
                f"id {challenge_id!r} does not match directory name {path.name!r}"
            )

        entry_file = str(raw.get("entry_file", "solution.py"))
        starter_path = path / STARTER_DIR / entry_file
        if not starter_path.is_file():
            raise ChallengeFormatError(f"starter file missing: {STARTER_DIR}/{entry_file}")

        description_path = path / DESCRIPTION_FILE
        if not description_path.is_file():
            raise ChallengeFormatError(f"missing {DESCRIPTION_FILE}")

        tests_dir = path / TESTS_DIR
        if not tests_dir.is_dir():
            raise ChallengeFormatError(f"missing {TESTS_DIR}/ directory")

        visible, hidden = _collect_tests(tests_dir)
        if not visible:
            raise ChallengeFormatError("challenge defines no visible tests")
        if not hidden:
            raise ChallengeFormatError("challenge defines no hidden tests")

        return LoadedChallenge(
            id=challenge_id,
            title=str(raw["title"]),
            summary=str(raw.get("summary", ""))[:400],
            difficulty=str(raw["difficulty"]),
            track=str(raw["track"]),
            module=str(raw.get("module", "General")),
            level=str(raw.get("level", "junior")),
            python_version=str(raw.get("python_version", "3.12")),
            time_limit_ms=int(raw.get("time_limit_ms", 5_000)),
            memory_limit_mb=int(raw.get("memory_limit_mb", 128)),
            points=int(raw.get("points", 100)),
            order_index=int(raw.get("order_index", 0)),
            skills=_string_list(raw.get("skills")),
            entry_file=entry_file,
            tags=_string_list(raw.get("tags")),
            path=path,
            files=ChallengeFiles(
                description=description_path.read_text(encoding="utf-8"),
                starter=starter_path.read_text(encoding="utf-8"),
                visible_tests=visible,
                hidden_tests=hidden,
            ),
        )


def _collect_tests(tests_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Split test files into visible and hidden buckets by filename prefix."""
    visible: dict[str, str] = {}
    hidden: dict[str, str] = {}
    for test_file in sorted(tests_dir.glob("test_*.py")):
        source = test_file.read_text(encoding="utf-8")
        if test_file.name.startswith(f"test_{HIDDEN_PREFIX}"):
            hidden[test_file.name] = source
        else:
            visible[test_file.name] = source
    return visible, hidden


def _slug(challenge_id: str, track: str) -> str:
    return challenge_id[len(track) + 1 :] if challenge_id.startswith(f"{track}-") else challenge_id


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, (str, int, float))]
    return []
