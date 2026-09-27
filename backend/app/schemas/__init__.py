"""Request/response schemas for the PyCraft API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.execution.models import ExecutionMode

# --- Common limits -------------------------------------------------------
MAX_FILES = 10
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 256 * 1024


class SubmissionRequest(BaseModel):
    """Payload for Run and Submit."""

    model_config = ConfigDict(extra="forbid")

    # Mapping of filename -> source. A mapping (not a single string) keeps
    # multi-file challenges possible without changing the contract.
    files: dict[str, str] = Field(..., min_length=1, max_length=MAX_FILES)
    # Optional client-side revision marker, echoed back for traceability.
    client_revision: int | None = None

    @field_validator("files")
    @classmethod
    def _validate_files(cls, files: dict[str, str]) -> dict[str, str]:
        total = 0
        for name, source in files.items():
            if not name.endswith(".py"):
                raise ValueError(f"file {name!r} must be a .py file")
            if "/" in name or "\\" in name or ".." in name:
                raise ValueError(f"file {name!r} must be a bare filename")
            if not source.strip():
                raise ValueError(f"file {name!r} is empty")
            size = len(source.encode("utf-8"))
            if size > MAX_FILE_BYTES:
                raise ValueError(f"file {name!r} exceeds {MAX_FILE_BYTES} bytes")
            total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError(f"submission exceeds {MAX_TOTAL_BYTES} bytes in total")
        return files


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


class ChallengeDetail(ChallengeSummary):
    description: str
    starter_code: str
    entry_file: str
    time_limit_ms: int
    memory_limit_mb: int
    visible_tests: dict[str, str]


class TestFileInfo(BaseModel):
    name: str
    source: str


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
