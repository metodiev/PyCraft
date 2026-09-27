"""Scoring: correctness weighting, performance tapering and quality heuristics."""

from __future__ import annotations

from app.execution.models import ExecutionReport, ExecutionStatus, TestOutcome, TestResult
from app.services.scoring import PASS_THRESHOLD, score_submission


def report(*outcomes: TestOutcome, elapsed_ms: int = 100) -> ExecutionReport:
    return ExecutionReport(
        status=ExecutionStatus.COMPLETED,
        tests=[
            TestResult(name=f"test_{i}", status=outcome, hidden=False)
            for i, outcome in enumerate(outcomes)
        ],
        execution_time_ms=elapsed_ms,
    )


def test_all_passed_beginner_scores_full_marks() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, TestOutcome.PASSED),
        difficulty="beginner",
        source="def f():\n    return 1\n",
        time_limit_ms=5000,
    )
    assert result.score == 100
    assert result.passed


def test_all_passed_but_placeholder_source_loses_quality_marks() -> None:
    result = score_submission(
        report(TestOutcome.PASSED),
        difficulty="advanced",
        source="def f():\n    # TODO: implement\n    raise NotImplementedError\n",
        time_limit_ms=5000,
    )
    assert result.score < 100
    quality = next(d for d in result.dimensions if d.name == "quality")
    assert quality.score < 100
    assert "placeholder" in quality.detail


def test_partial_visible_failure_blocks_pass() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, TestOutcome.FAILED),
        difficulty="beginner",
        source="def f():\n    return 1\n",
        time_limit_ms=5000,
    )
    assert result.score == 50
    assert not result.passed


def test_hidden_tests_weigh_more_than_visible() -> None:
    # One visible pass, one hidden fail: 40% of correctness earned.
    partial = score_submission(
        report(TestOutcome.PASSED, TestOutcome.FAILED),
        difficulty="beginner",
        source="x = 1",
        time_limit_ms=5000,
        hidden_total=1,
        hidden_passed=0,
    )
    assert partial.score == 40

    # One visible fail, one hidden pass: 60% of correctness earned.
    better = score_submission(
        report(TestOutcome.PASSED, TestOutcome.FAILED),
        difficulty="beginner",
        source="x = 1",
        time_limit_ms=5000,
        hidden_total=1,
        hidden_passed=1,
    )
    assert better.score == 60


def test_hidden_weighting_cannot_exceed_bounds() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, TestOutcome.PASSED),
        difficulty="beginner",
        source="x = 1",
        time_limit_ms=5000,
        hidden_total=1,
        hidden_passed=1,
    )
    assert 0 <= result.score <= 100


def test_timeout_scores_zero() -> None:
    timed_out = ExecutionReport(status=ExecutionStatus.TIMEOUT)
    result = score_submission(
        timed_out, difficulty="beginner", source="x = 1", time_limit_ms=5000
    )
    assert result.score == 0
    assert not result.passed
    assert "time limit" in result.summary.lower()


def test_runner_failure_scores_zero() -> None:
    failed = ExecutionReport(status=ExecutionStatus.FAILED, error_message="ImportError: nope")
    result = score_submission(
        failed, difficulty="beginner", source="x = 1", time_limit_ms=5000
    )
    assert result.score == 0
    assert "nope" in result.summary


def test_no_tests_run_scores_zero() -> None:
    empty = ExecutionReport(status=ExecutionStatus.COMPLETED, tests=[])
    result = score_submission(
        empty, difficulty="beginner", source="x = 1", time_limit_ms=5000
    )
    assert result.score == 0


def test_performance_tapers_near_the_limit() -> None:
    fast = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=100),
        difficulty="easy",
        source="x = 1",
        time_limit_ms=5000,
    )
    slow = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=4800),
        difficulty="easy",
        source="x = 1",
        time_limit_ms=5000,
    )

    assert fast.score > slow.score
    fast_perf = next(d for d in fast.dimensions if d.name == "performance")
    slow_perf = next(d for d in slow.dimensions if d.name == "performance")
    assert fast_perf.score == 100
    assert slow_perf.score < 50


def test_performance_is_full_below_floor_ratio() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=1000),
        difficulty="easy",
        source="x = 1",
        time_limit_ms=5000,
    )
    performance = next(d for d in result.dimensions if d.name == "performance")
    assert performance.score == 100


def test_beginner_only_scores_correctness() -> None:
    result = score_submission(
        report(TestOutcome.PASSED),
        difficulty="beginner",
        source="x = 1",
        time_limit_ms=5000,
    )
    assert [d.name for d in result.dimensions] == ["correctness"]


def test_advanced_includes_quality_and_performance() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=100),
        difficulty="advanced",
        source='"""Documented."""\n\ndef f():\n    """Return one."""\n    return 1\n',
        time_limit_ms=5000,
    )
    assert {d.name for d in result.dimensions} == {"correctness", "performance", "quality"}


def test_unparseable_source_loses_all_quality_marks() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=100),
        difficulty="expert",
        source="def broken(:\n",
        time_limit_ms=5000,
    )
    quality = next(d for d in result.dimensions if d.name == "quality")
    assert quality.score == 0
    assert "does not parse" in quality.detail


def test_pass_threshold_is_inclusive() -> None:
    result = score_submission(
        report(TestOutcome.PASSED),
        difficulty="beginner",
        source="x = 1",
        time_limit_ms=5000,
    )
    assert result.score >= PASS_THRESHOLD
    assert result.passed


def test_documented_source_scores_full_quality() -> None:
    result = score_submission(
        report(TestOutcome.PASSED, elapsed_ms=100),
        difficulty="advanced",
        source='"""A module."""\n\ndef f():\n    """A function."""\n    return 1\n',
        time_limit_ms=5000,
    )
    quality = next(d for d in result.dimensions if d.name == "quality")
    assert quality.score == 100
