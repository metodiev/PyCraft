"""The PyCraft learning roadmap.

Defines the progression from first steps to principal engineer, the skill graph
behind it, and which challenges belong to which stage. Kept as data (not code)
so the roadmap can be re-curated without touching business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RoadmapStage:
    """One stage of the engineering progression."""

    id: str
    title: str
    description: str
    level: str  # junior | intermediate | senior | staff | principal
    # Skill node this stage primarily develops.
    skill: str
    # Ordered list of stages this one depends on.
    requires: tuple[str, ...] = ()


ROADMAP: tuple[RoadmapStage, ...] = (
    RoadmapStage(
        id="python-fundamentals",
        title="Python Fundamentals",
        description="Syntax, types, control flow, functions, collections and the standard library.",
        level="junior",
        skill="python.fundamentals",
    ),
    RoadmapStage(
        id="professional-python",
        title="Professional Python",
        description="Typing, dataclasses, decorators, generators, context managers and Python internals.",
        level="junior",
        skill="python.professional",
        requires=("python-fundamentals",),
    ),
    RoadmapStage(
        id="testing-quality",
        title="Testing & Quality",
        description="pytest, fixtures, mocking, property-based testing and CI quality gates.",
        level="intermediate",
        skill="testing",
        requires=("professional-python",),
    ),
    RoadmapStage(
        id="web-development",
        title="Web Development",
        description="HTTP, FastAPI, Flask, Django, DRF, authentication and API design.",
        level="intermediate",
        skill="web",
        requires=("testing-quality",),
    ),
    RoadmapStage(
        id="databases",
        title="Databases",
        description="SQL, PostgreSQL, SQLAlchemy, transactions, indexes and query optimisation.",
        level="intermediate",
        skill="databases",
        requires=("web-development",),
    ),
    RoadmapStage(
        id="async-concurrency",
        title="Async & Concurrency",
        description="asyncio, threading, multiprocessing, cancellation and backpressure.",
        level="senior",
        skill="async",
        requires=("databases",),
    ),
    RoadmapStage(
        id="backend-engineering",
        title="Backend Engineering",
        description="Caching, messaging, Celery, Redis, Kafka and production service design.",
        level="senior",
        skill="backend",
        requires=("async-concurrency",),
    ),
    RoadmapStage(
        id="performance",
        title="Performance",
        description="Profiling, algorithmic complexity, memory behaviour and optimisation.",
        level="senior",
        skill="performance",
        requires=("backend-engineering",),
    ),
    RoadmapStage(
        id="cloud-devops",
        title="Cloud & DevOps",
        description="Docker, Kubernetes, Terraform, CI/CD and observability.",
        level="senior",
        skill="devops",
        requires=("performance",),
    ),
    RoadmapStage(
        id="distributed-systems",
        title="Distributed Systems",
        description="Consistency, partitioning, idempotency, consensus and failure modes.",
        level="staff",
        skill="distributed",
        requires=("cloud-devops",),
    ),
    RoadmapStage(
        id="system-design",
        title="System Design",
        description="Capacity planning, trade-off analysis, scalability and reliability engineering.",
        level="staff",
        skill="system_design",
        requires=("distributed-systems",),
    ),
    RoadmapStage(
        id="software-architecture",
        title="Software Architecture",
        description="SOLID, Clean/Hexagonal architecture, DDD, CQRS and event-driven design.",
        level="principal",
        skill="architecture",
        requires=("system-design",),
    ),
    RoadmapStage(
        id="principal-engineer",
        title="Principal Engineer",
        description="Organisation-scale technical strategy, resilience, security, cost and maintainability.",
        level="principal",
        skill="leadership",
        requires=("software-architecture",),
    ),
)

STAGES_BY_ID: dict[str, RoadmapStage] = {stage.id: stage for stage in ROADMAP}

# Developer levels with the XP required to reach them.
LEVELS: tuple[tuple[str, str, int], ...] = (
    ("junior", "Junior", 0),
    ("intermediate", "Intermediate", 1_000),
    ("senior", "Senior", 3_000),
    ("staff", "Staff", 7_000),
    ("principal", "Principal / Architect", 15_000),
)

SKILL_LABELS: dict[str, str] = {
    stage.skill: stage.title for stage in ROADMAP
} | {
    "python.basics": "Python Basics",
}


@dataclass(frozen=True, slots=True)
class RoadmapView:
    """A roadmap stage annotated with the viewer's progress."""

    id: str
    title: str
    description: str
    level: str
    skills: list[str] = field(default_factory=list)
    total_challenges: int = 0
    completed_challenges: int = 0
    locked: bool = False

    @property
    def progress_pct(self) -> int:
        if self.total_challenges == 0:
            return 0
        return round(self.completed_challenges / self.total_challenges * 100)


def level_for_xp(xp: int) -> tuple[str, str, int]:
    """Return ``(level_id, level_label, xp_into_level)`` for a total XP value."""
    current = LEVELS[0]
    for candidate in LEVELS:
        if xp >= candidate[2]:
            current = candidate
    return current[0], current[1], xp - current[2]


def next_level(xp: int) -> tuple[str, int] | None:
    """Return ``(label, xp_required)`` for the next level, or ``None`` at the top."""
    for _level_id, label, required in LEVELS:
        if xp < required:
            return label, required
    return None
