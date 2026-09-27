"""Request/response schemas for the PyCraft API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.execution.models import ExecutionMode

# --- Common limits -------------------------------------------------------
MAX_FILES = 25
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 512 * 1024
# A project may nest modules a couple of levels, not arbitrarily deep.
MAX_PATH_DEPTH = 4


class SubmissionRequest(BaseModel):
    """Payload for Run and Submit."""

    model_config = ConfigDict(extra="forbid")

    # Mapping of filename -> source. A mapping (not a single string) is what
    # makes multi-file projects possible without changing the contract.
    files: dict[str, str] = Field(..., min_length=1, max_length=MAX_FILES)
    # Optional client-side revision marker, echoed back for traceability.
    client_revision: int | None = None

    @field_validator("files")
    @classmethod
    def _validate_files(cls, files: dict[str, str]) -> dict[str, str]:
        """Validate filenames and sizes.

        Nested paths are permitted here because project challenges submit
        several modules; whether nesting is *appropriate* is decided by the
        endpoint, which knows if the challenge is a project.
        """
        total = 0
        for name, source in files.items():
            if not name.endswith(".py"):
                raise ValueError(f"file {name!r} must be a .py file")
            parts = name.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                raise ValueError(f"file {name!r} has an unsafe path")
            if any(part.startswith(".") for part in parts):
                raise ValueError(f"file {name!r} must not be hidden")
            if len(parts) > MAX_PATH_DEPTH:
                raise ValueError(f"file {name!r} is nested too deeply")
            if not source.strip():
                raise ValueError(f"file {name!r} is empty")
            size = len(source.encode("utf-8"))
            if size > MAX_FILE_BYTES:
                raise ValueError(f"file {name!r} exceeds {MAX_FILE_BYTES} bytes")
            total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"submission exceeds {MAX_TOTAL_BYTES} bytes in total")
        return files


def reject_nested_paths(files: dict[str, str]) -> None:
    """Refuse nested filenames for single-file challenges.

    Kept out of the schema because only the endpoint knows the challenge kind.
    Raises ``ValueError`` with a message suitable for a 4xx response.
    """
    for name in files:
        if "/" in name:
            raise ValueError(
                f"file {name!r} must be a bare filename; this challenge accepts "
                "a single file"
            )


class TestResultSchema(BaseModel):
    name: str
    status: str
    duration_ms: int = 0
    message: str = ""
    hidden: bool = False


class RunResponse(BaseModel):
    """Result of an experimental Run — no scoring, no persistence of progress."""

    submission_id: uuid.UUID
    status: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    execution_time_ms: int = 0
    memory_used_mb: float = 0.0


class SubmitResponse(BaseModel):
    """Result of a graded Submit."""

    submission_id: uuid.UUID
    status: str
    score: int
    passed: int
    failed: int
    total_tests: int
    execution_time_ms: int
    memory_used_mb: float
    results: list[TestResultSchema]
    dimensions: list[dict] = Field(default_factory=list)
    summary: str = ""
    progress: ProgressSummary | None = None
    # Achievements unlocked by this submission, so the UI can celebrate them.
    newly_unlocked: list[dict] = Field(default_factory=list)


class ChallengeSummary(BaseModel):
    id: str
    title: str
    summary: str
    difficulty: str
    track: str
    module: str
    level: str
    python_version: str
    points: int
    order_index: int
    skills: list[str]
    tags: list[str]
    visible_test_count: int
    skill_mastery: int = 0
    completed: bool = False
    best_score: int = 0
    kind: str = "challenge"
    is_project: bool = False


class ChallengeDetail(ChallengeSummary):
    description: str
    starter_code: str
    entry_file: str
    time_limit_ms: int
    memory_limit_mb: int
    visible_tests: dict[str, str]
    # "challenge" or "project"; projects expose several editable files.
    kind: str = "challenge"
    is_project: bool = False
    # Filename -> source, for every file the learner may edit.
    starter_files: dict[str, str] = Field(default_factory=dict)
    # Documents why a project is scored as it is; grading stays test-driven.
    rubric: list[dict] = Field(default_factory=list)


class TestFileInfo(BaseModel):
    name: str
    source: str


class QueuedResponse(BaseModel):
    """Acknowledgement that a submission is queued for execution.

    Returned with ``202 Accepted``. The caller polls ``submission_url`` until
    ``status`` is terminal; nothing has executed yet when this is sent.
    """

    submission_id: uuid.UUID
    status: str
    #: Where to poll. Sent so a client never has to construct the path itself.
    submission_url: str
    #: Queue position at the time of the request, for an honest "you are Nth".
    queue_depth: int = 0


class ProgressSummary(BaseModel):
    xp: int
    level_id: str
    level_label: str
    xp_into_level: int
    next_level_label: str | None = None
    next_level_xp: int | None = None
    completed_challenges: int
    total_challenges: int
    completion_pct: int


class SubmissionStatusResponse(BaseModel):
    """The state of one submission, for polling.

    ``RunResponse``/``SubmitResponse`` fields are absent until the submission
    reaches a terminal status, so a poller can tell "still working" from
    "finished" by checking ``status`` rather than by looking for missing keys.
    """

    submission_id: uuid.UUID
    kind: str
    status: str
    done: bool
    challenge_id: str
    created_at: datetime
    finished_at: datetime | None = None
    error_message: str | None = None

    # Run detail.
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None

    # Submit detail, populated only once grading has run.
    score: int | None = None
    passed: int = 0
    failed: int = 0
    total_tests: int = 0
    results: list[TestResultSchema] = Field(default_factory=list)
    dimensions: list[dict] = Field(default_factory=list)
    summary: str = ""
    progress: ProgressSummary | None = None
    newly_unlocked: list[dict] = Field(default_factory=list)

    execution_time_ms: int | None = None
    memory_used_mb: float | None = None


class SkillBar(BaseModel):
    skill: str
    label: str
    mastery: int
    xp: int
    challenges_completed: int = 0
    challenges_total: int = 0


class RoadmapStageSchema(BaseModel):
    id: str
    title: str
    description: str
    level: str
    progress_pct: int
    total_challenges: int
    completed_challenges: int
    locked: bool


class RecentSubmission(BaseModel):
    id: uuid.UUID
    challenge_id: str
    challenge_title: str
    kind: str
    status: str
    score: int | None
    passed: int
    failed: int
    total_tests: int
    execution_time_ms: int | None
    created_at: datetime


class DashboardResponse(BaseModel):
    progress: ProgressSummary
    skills: list[SkillBar]
    roadmap: list[RoadmapStageSchema]
    recent_submissions: list[RecentSubmission]
    recommended_challenge: ChallengeSummary | None = None
    continue_challenge: ChallengeSummary | None = None


class RuntimeInfo(BaseModel):
    execution_backend: str
    python_versions: list[str]
    default_python_version: str
    environment: str
    challenge_count: int


__all__ = [
    "ChallengeDetail",
    "ChallengeSummary",
    "DashboardResponse",
    "ExecutionMode",
    "ProgressSummary",
    "RecentSubmission",
    "RoadmapStageSchema",
    "RunResponse",
    "RuntimeInfo",
    "SkillBar",
    "SubmissionRequest",
    "SubmitResponse",
    "TestFileInfo",
    "TestResultSchema",
]
