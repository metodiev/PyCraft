"""Challenge authoring: draft storage, validation and publishing.

Authored challenges are written to disk in exactly the format the loader reads,
so an author's work is reviewable in a pull request like any other content. The
database holds only *drafts in progress*, which lets the authoring UI autosave
without creating spurious git churn.

**Validation happens before publishing, never at read time.** A half-written
draft must not be able to break the catalogue for every learner.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from app.services.challenges import (
    DESCRIPTION_FILE,
    METADATA_FILE,
    STARTER_DIR,
    TESTS_DIR,
    ChallengeFormatError,
    ChallengeRepository,
)

logger = logging.getLogger(__name__)

# Slugs become directory names, so keep them to a conservative character set.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LENGTH = 60
MAX_TITLE_LENGTH = 200
MAX_SUMMARY_LENGTH = 400
MAX_SOURCE_BYTES = 64 * 1024
MAX_TEST_FILES = 20

VALID_DIFFICULTIES = ("beginner", "easy", "intermediate", "advanced", "expert")
VALID_LEVELS = ("junior", "intermediate", "senior", "staff", "principal")

# Tracks must exist in the roadmap so the catalogue stays coherent.
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


class AuthoringError(ValueError):
    """Raised when a draft cannot be accepted."""


@dataclass(slots=True)
class ValidationIssue:
    """One problem found in a draft, tied to the field that caused it."""

    field: str
    message: str
    severity: str = "error"  # "error" blocks publishing, "warning" does not


@dataclass(slots=True)
class ChallengeDraft:
    """An in-progress challenge, as edited in the authoring UI."""

    slug: str
    track: str
    title: str = ""
    summary: str = ""
    difficulty: str = "beginner"
    level: str = "junior"
    module: str = "General"
    points: int = 50
    order_index: int = 1
    time_limit_ms: int = 5_000
    memory_limit_mb: int = 128
    python_version: str = "3.12"
    skills: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""
    starter_code: str = ""
    visible_tests: dict[str, str] = field(default_factory=dict)
    hidden_tests: dict[str, str] = field(default_factory=dict)

    @property
    def challenge_id(self) -> str:
        return f"{self.track}-{self.slug}"

    def to_metadata(self) -> dict[str, object]:
        """Produce the exact ``metadata.json`` the loader expects."""
        return {
            "id": self.challenge_id,
            "title": self.title,
            "summary": self.summary[:MAX_SUMMARY_LENGTH],
            "difficulty": self.difficulty,
            "track": self.track,
            "module": self.module,
            "level": self.level,
            "python_version": self.python_version,
            "time_limit_ms": self.time_limit_ms,
            "memory_limit_mb": self.memory_limit_mb,
            "points": self.points,
            "order_index": self.order_index,
            "skills": self.skills,
            "tags": self.tags,
            "entry_file": "solution.py",
        }


# --- validation ----------------------------------------------------------
def validate_draft(draft: ChallengeDraft) -> list[ValidationIssue]:
    """Check a draft without touching disk.

    Returns every issue found rather than raising on the first, so the UI can
    highlight all the problems at once.
    """
    issues: list[ValidationIssue] = []

    # --- identity ---
    if not draft.slug:
        issues.append(ValidationIssue("slug", "A slug is required"))
    elif not SLUG_PATTERN.match(draft.slug):
        issues.append(
            ValidationIssue(
                "slug",
                "Slug must be lowercase letters, numbers and single hyphens "
                "(e.g. 'lru-cache')",
            )
        )
    elif len(draft.slug) > MAX_SLUG_LENGTH:
        issues.append(ValidationIssue("slug", f"Slug must be at most {MAX_SLUG_LENGTH} characters"))

    if draft.track not in ALLOWED_TRACKS:
        issues.append(
            ValidationIssue(
                "track",
                f"Unknown track {draft.track!r}. Valid tracks: {', '.join(ALLOWED_TRACKS)}",
            )
        )

    # --- descriptive fields ---
    if not draft.title.strip():
        issues.append(ValidationIssue("title", "A title is required"))
    elif len(draft.title) > MAX_TITLE_LENGTH:
        issues.append(ValidationIssue("title", f"Title must be at most {MAX_TITLE_LENGTH} characters"))

    if not draft.summary.strip():
        issues.append(ValidationIssue("summary", "A one-sentence summary is required"))
    elif len(draft.summary) > MAX_SUMMARY_LENGTH:
        issues.append(
            ValidationIssue("summary", f"Summary must be at most {MAX_SUMMARY_LENGTH} characters")
        )

    if draft.difficulty not in VALID_DIFFICULTIES:
        issues.append(
            ValidationIssue(
                "difficulty", f"Difficulty must be one of: {', '.join(VALID_DIFFICULTIES)}"
            )
        )
    if draft.level not in VALID_LEVELS:
        issues.append(ValidationIssue("level", f"Level must be one of: {', '.join(VALID_LEVELS)}"))

    if len(draft.description.strip()) < 40:
        issues.append(
            ValidationIssue(
                "description",
                "The description looks too short. It should state the task, show "
                "examples and offer hints.",
            )
        )

    # --- limits ---
    if draft.points < 0 or draft.points > 1000:
        issues.append(ValidationIssue("points", "Points must be between 0 and 1000"))
    if draft.time_limit_ms < 500 or draft.time_limit_ms > 30_000:
        issues.append(ValidationIssue("time_limit_ms", "Time limit must be between 500 and 30000 ms"))
    if draft.memory_limit_mb < 32 or draft.memory_limit_mb > 1024:
        issues.append(ValidationIssue("memory_limit_mb", "Memory limit must be between 32 and 1024 MB"))

    # --- code ---
    if not draft.starter_code.strip():
        issues.append(ValidationIssue("starter_code", "Starter code is required"))

    if not draft.visible_tests:
        issues.append(ValidationIssue("visible_tests", "At least one visible test is required"))
    if not draft.hidden_tests:
        issues.append(
            ValidationIssue(
                "hidden_tests",
                "At least one hidden test is required — they are what makes the "
                "challenge meaningful.",
            )
        )

    for group_name, files in (("visible_tests", draft.visible_tests), ("hidden_tests", draft.hidden_tests)):
        issues.extend(_validate_tests(group_name, files))

    # --- guidance (non-blocking) ---
    if len(draft.hidden_tests) < len(draft.visible_tests):
        issues.append(
            ValidationIssue(
                "hidden_tests",
                "Consider adding more hidden than visible tests, so learners cannot "
                "pass by satisfying only the tests they can see.",
                severity="warning",
            )
        )
    if not draft.skills:
        issues.append(
            ValidationIssue(
                "skills",
                "No skills listed — this challenge will not contribute to the learner's "
                "skill graph.",
                severity="warning",
            )
        )

    return issues


def _validate_tests(group_name: str, files: dict[str, str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if len(files) > MAX_TEST_FILES:
        issues.append(
            ValidationIssue(group_name, f"At most {MAX_TEST_FILES} test files are allowed")
        )

    for name, source in files.items():
        if not name.endswith(".py"):
            issues.append(ValidationIssue(group_name, f"{name!r} must be a .py file"))
        if not name.startswith("test_"):
            issues.append(
                ValidationIssue(
                    group_name,
                    f"{name!r} must start with 'test_' or pytest will not collect it",
                )
            )
        if "/" in name or "\\" in name or ".." in name:
            issues.append(ValidationIssue(group_name, f"{name!r} must be a bare filename"))
        if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
            issues.append(ValidationIssue(group_name, f"{name!r} is too large"))
        if "from solution import" not in source and "import solution" not in source:
            issues.append(
                ValidationIssue(
                    group_name,
                    f"{name!r} does not import from the solution module. Tests must "
                    "start with 'from solution import ...'.",
                    severity="warning",
                )
            )
        issues.extend(_forbidden_imports(group_name, name, source))

    return issues


# The sandbox has no network and only the standard library, so a test that
# reaches for these would fail at run time with a confusing error.
_FORBIDDEN_IMPORTS = (
    "requests",
    "httpx",
    "numpy",
    "pandas",
    "fastapi",
    "sqlalchemy",
    "django",
    "flask",
    "redis",
    "kafka",
    "boto3",
    "docker",
)


def _forbidden_imports(group_name: str, name: str, source: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for module in _FORBIDDEN_IMPORTS:
        pattern = rf"^\s*(?:import\s+{module}\b|from\s+{module}\b)"
        if re.search(pattern, source, re.MULTILINE):
            issues.append(
                ValidationIssue(
                    group_name,
                    f"{name!r} imports {module!r}, which is not available in the "
                    "execution sandbox. Standard library only.",
                )
            )
    return issues


def blocking_issues(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.severity == "error"]


# --- publishing ----------------------------------------------------------
def publish_draft(draft: ChallengeDraft, challenges_root: Path, *, overwrite: bool = True) -> Path:
    """Write a validated draft to disk in the loader's format.

    The write is staged in a temporary directory and moved into place, so a
    crash mid-write cannot leave a half-written challenge in the catalogue.
    """
    issues = blocking_issues(validate_draft(draft))
    if issues:
        summary = "; ".join(f"{issue.field}: {issue.message}" for issue in issues)
        raise AuthoringError(f"Draft has validation errors — {summary}")

    target = challenges_root / draft.track / draft.slug
    if target.exists() and not overwrite:
        raise AuthoringError(f"A challenge already exists at {draft.track}/{draft.slug}")

    staging = target.with_name(f".{draft.slug}.staging")
    if staging.exists():
        shutil.rmtree(staging)
    (staging / STARTER_DIR).mkdir(parents=True)
    (staging / TESTS_DIR).mkdir(parents=True)

    (staging / METADATA_FILE).write_text(
        json.dumps(draft.to_metadata(), indent=2) + "\n", encoding="utf-8"
    )
    (staging / DESCRIPTION_FILE).write_text(draft.description, encoding="utf-8")
    (staging / STARTER_DIR / "solution.py").write_text(draft.starter_code, encoding="utf-8")

    for name, source in draft.visible_tests.items():
        (staging / TESTS_DIR / name).write_text(source, encoding="utf-8")
    for name, source in draft.hidden_tests.items():
        (staging / TESTS_DIR / name).write_text(source, encoding="utf-8")

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)

    logger.info("Published challenge %s to %s", draft.challenge_id, target)
    return target


def load_draft(challenges_root: Path, track: str, slug: str) -> ChallengeDraft | None:
    """Read a published challenge back into editable form."""
    path = challenges_root / track / slug
    if not (path / METADATA_FILE).is_file():
        return None

    raw = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
    visible: dict[str, str] = {}
    hidden: dict[str, str] = {}
    tests_dir = path / TESTS_DIR
    if tests_dir.is_dir():
        for test_file in sorted(tests_dir.glob("test_*.py")):
            source = test_file.read_text(encoding="utf-8")
            if test_file.name.startswith("test_hidden"):
                hidden[test_file.name] = source
            else:
                visible[test_file.name] = source

    starter_path = path / STARTER_DIR / str(raw.get("entry_file", "solution.py"))
    description_path = path / DESCRIPTION_FILE

    return ChallengeDraft(
        slug=slug,
        track=track,
        title=str(raw.get("title", "")),
        summary=str(raw.get("summary", "")),
        difficulty=str(raw.get("difficulty", "beginner")),
        level=str(raw.get("level", "junior")),
        module=str(raw.get("module", "General")),
        points=int(raw.get("points", 50)),
        order_index=int(raw.get("order_index", 1)),
        time_limit_ms=int(raw.get("time_limit_ms", 5_000)),
        memory_limit_mb=int(raw.get("memory_limit_mb", 128)),
        python_version=str(raw.get("python_version", "3.12")),
        skills=_string_list(raw.get("skills")),
        tags=_string_list(raw.get("tags")),
        description=description_path.read_text(encoding="utf-8") if description_path.is_file() else "",
        starter_code=starter_path.read_text(encoding="utf-8") if starter_path.is_file() else "",
        visible_tests=visible,
        hidden_tests=hidden,
    )


def _string_list(value: object) -> list[str]:
    """Coerce a metadata list field, tolerating a wrong type in hand-edited files."""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def refresh_catalogue(repository: ChallengeRepository) -> list[str]:
    """Re-read all challenges from disk after a publish.

    Returns the ids that are now present so the caller can report what changed.
    """
    loaded = repository.load_all()
    return [challenge.id for challenge in loaded]


def draft_from_payload(payload: object) -> ChallengeDraft:
    """Build a draft from an untrusted request body.

    Raises:
        AuthoringError: if the payload is not an object or a field has the wrong
            type. Field-level *content* problems are reported by
            :func:`validate_draft` instead.
    """
    if not isinstance(payload, dict):
        raise AuthoringError("Expected a JSON object")

    def text(key: str, default: str = "") -> str:
        value = payload.get(key, default)
        if value is None:
            return default
        if not isinstance(value, str):
            raise AuthoringError(f"Field {key!r} must be a string")
        return value

    def integer(key: str, default: int) -> int:
        value = payload.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise AuthoringError(f"Field {key!r} must be a number")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise AuthoringError(f"Field {key!r} must be a number") from exc

    def string_list(key: str) -> list[str]:
        value = payload.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise AuthoringError(f"Field {key!r} must be a list of strings")
        return [str(item) for item in value]

    def source_map(key: str) -> dict[str, str]:
        value = payload.get(key, {})
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise AuthoringError(f"Field {key!r} must be an object of filename -> source")
        result: dict[str, str] = {}
        for name, source in value.items():
            if not isinstance(source, str):
                raise AuthoringError(f"Test {name!r} must contain source text")
            result[str(name)] = source
        return result

    return ChallengeDraft(
        slug=text("slug"),
        track=text("track"),
        title=text("title"),
        summary=text("summary"),
        difficulty=text("difficulty", "beginner"),
        level=text("level", "junior"),
        module=text("module", "General"),
        points=integer("points", 50),
        order_index=integer("order_index", 1),
        time_limit_ms=integer("time_limit_ms", 5_000),
        memory_limit_mb=integer("memory_limit_mb", 128),
        python_version=text("python_version", "3.12"),
        skills=string_list("skills"),
        tags=string_list("tags"),
        description=text("description"),
        starter_code=text("starter_code"),
        visible_tests=source_map("visible_tests"),
        hidden_tests=source_map("hidden_tests"),
    )


__all__ = [
    "ALLOWED_TRACKS",
    "AuthoringError",
    "ChallengeDraft",
    "ChallengeFormatError",
    "ValidationIssue",
    "blocking_issues",
    "draft_from_payload",
    "load_draft",
    "publish_draft",
    "refresh_catalogue",
    "validate_draft",
]
