"""Multi-dimensional scoring.

The spec calls for more than pass/fail: correctness, performance, code quality,
test quality, security and architecture. Only *correctness* and *performance*
can be measured objectively from a sandbox run today; the rest are declared as
pluggable dimensions so static-analysis and review signals can be added without
changing the API contract.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from app.execution.models import ExecutionReport, ExecutionStatus

# Weighting per difficulty. Beginner work is graded almost entirely on
# correctness; advanced work rewards efficiency and quality.
WEIGHTS: dict[str, dict[str, int]] = {
    "beginner": {"correctness": 100},
    "easy": {"correctness": 85, "performance": 15},
    "intermediate": {"correctness": 75, "performance": 15, "quality": 10},
    "advanced": {"correctness": 65, "performance": 15, "quality": 20},
    "expert": {"correctness": 55, "performance": 20, "quality": 25},
}
DEFAULT_WEIGHTS = WEIGHTS["beginner"]

# Earned points are scaled down below this score so partial credit stays honest.
PASS_THRESHOLD = 60

# A submission slower than this fraction of the limit starts losing
# performance marks; at the limit itself the hint of a timeout is real.
PERFORMANCE_FLOOR_RATIO = 0.25


@dataclass(slots=True)
class Dimension:
    """One scored aspect of a submission."""

    name: str
    score: int
    weight: int
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(slots=True)
class ScoringResult:
    """Final grade for a submission."""

    score: int
    passed: bool
    dimensions: list[Dimension] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "passed": self.passed,
            "summary": self.summary,
            "dimensions": [d.to_dict() for d in self.dimensions],
        }


def score_submission(
    report: ExecutionReport,
    *,
    difficulty: str,
    source: str = "",
    time_limit_ms: int,
    hidden_total: int = 0,
    hidden_passed: int = 0,
) -> ScoringResult:
    """Grade a submission across the dimensions measurable today."""
    weights = WEIGHTS.get(difficulty, DEFAULT_WEIGHTS)
    dimensions: list[Dimension] = []

    if report.status is ExecutionStatus.TIMEOUT:
        return ScoringResult(
            score=0,
            passed=False,
            dimensions=[
                Dimension("correctness", 0, weights.get("correctness", 100), "Time limit exceeded")
            ],
            summary="Execution exceeded the time limit.",
        )

    if report.status is not ExecutionStatus.COMPLETED or report.total == 0:
        return ScoringResult(
            score=0,
            passed=False,
            dimensions=[
                Dimension(
                    "correctness",
                    0,
                    weights.get("correctness", 100),
                    report.error_message or "Tests did not run",
                )
            ],
            summary=report.error_message or "The submission could not be evaluated.",
        )

    correctness = _correctness_score(report, hidden_total, hidden_passed)
    dimensions.append(
        Dimension(
            "correctness",
            correctness,
            weights.get("correctness", 100),
            f"{report.passed}/{report.total} tests passed",
        )
    )

    if "performance" in weights:
        dimensions.append(
            Dimension(
                "performance",
                _performance_score(report.execution_time_ms, time_limit_ms),
                weights["performance"],
                f"Completed in {report.execution_time_ms} ms",
            )
        )

    if "quality" in weights:
        score, detail = _quality_score(source)
        dimensions.append(Dimension("quality", score, weights["quality"], detail))

    total_weight = sum(d.weight for d in dimensions) or 1
    weighted = sum(d.score * d.weight for d in dimensions) / total_weight
    final = max(0, min(100, round(weighted)))

    return ScoringResult(
        score=final,
        passed=final >= PASS_THRESHOLD and report.failed == 0,
        dimensions=dimensions,
        summary=_summarise(final, report, correct=report.failed == 0),
    )


def _correctness_score(report: ExecutionReport, hidden_total: int, hidden_passed: int) -> int:
    """Weight hidden tests more heavily than the ones the learner can iterate on."""
    if hidden_total > 0:
        visible_total = report.total - hidden_total
        visible_passed = report.passed - hidden_passed
        visible_ratio = (visible_passed / visible_total) if visible_total else 1.0
        hidden_ratio = hidden_passed / hidden_total
        # 60% hidden / 40% visible: clearing the unseen suite is what proves mastery.
        return round(max(0.0, min(1.0, 0.4 * visible_ratio + 0.6 * hidden_ratio)) * 100)

    ratio = report.passed / report.total if report.total else 0
    return round(max(0.0, min(1.0, ratio)) * 100)


def _performance_score(execution_ms: int, time_limit_ms: int) -> int:
    """Full marks well below the limit, tapering to zero as it is approached."""
    if time_limit_ms <= 0:
        return 100
    used = execution_ms / time_limit_ms
    if used <= PERFORMANCE_FLOOR_RATIO:
        return 100
    if used >= 1:
        return 0
    span = 1 - PERFORMANCE_FLOOR_RATIO
    return round((1 - (used - PERFORMANCE_FLOOR_RATIO) / span) * 100)


_PLACEHOLDER = re.compile(r"\b(todo|fixme|hack|xxx)\b", re.IGNORECASE)


def _quality_score(source: str) -> tuple[int, str]:
    """Heuristic quality signal: parses cleanly, documented, no placeholders."""
    if not source.strip():
        return 0, "No source provided"

    score = 100
    notes: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0, "Source does not parse"

    if _PLACEHOLDER.search(source):
        score -= 25
        notes.append("placeholder comments left in code")
    if _has_placeholder_raise(tree):
        score -= 40
        notes.append("starter NotImplementedError still present")
    if not _has_docstring_or_comments(tree, source):
        score -= 15
        notes.append("no documentation")

    return max(0, score), ", ".join(notes) or "Readable, documented, no placeholders"


def _has_placeholder_raise(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc
            name = (
                exc.func.id
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name)
                else getattr(exc, "id", None)
            )
            if name == "NotImplementedError":
                return True
    return False


def _has_docstring_or_comments(tree: ast.AST, source: str) -> bool:
    if ast.get_docstring(tree):
        return True
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and ast.get_docstring(node)
        for node in ast.walk(tree)
    ) or "#" in source


def _summarise(score: int, report: ExecutionReport, *, correct: bool) -> str:
    if correct and score >= 90:
        return f"Excellent — all {report.total} tests passed."
    if correct:
        return f"All {report.total} tests passed."
    failed = report.failed
    return f"{failed} of {report.total} tests failed."
