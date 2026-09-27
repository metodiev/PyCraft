"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import detect_flaky


def test_skipped_runs_are_invisible():
    history = [{"a": "passed"}, {"a": "skipped"}, {"a": "failed"}, {"a": "skipped"}]
    assert detect_flaky(history) == {
        "a": {"outcomes": {"passed": 1, "failed": 1}, "flips": 1, "first_flip_run": 2}
    }


def test_only_ever_passed_or_skipped_is_not_flaky():
    assert detect_flaky([{"a": "passed"}, {"a": "skipped"}, {"a": "passed"}]) == {}
    assert detect_flaky([{"a": "failed"}, {"a": "failed"}]) == {}


def test_missing_tests_behave_like_skips():
    history = [{"a": "passed"}, {"b": "passed"}, {"a": "failed"}]
    assert detect_flaky(history) == {
        "a": {"outcomes": {"passed": 1, "failed": 1}, "flips": 1, "first_flip_run": 2}
    }


def test_flips_count_only_consecutive_executed_outcomes():
    history = [
        {"a": "passed"},
        {"a": "skipped"},
        {"a": "passed"},
        {"a": "failed"},
        {"a": "failed"},
        {"a": "passed"},
    ]
    result = detect_flaky(history)["a"]
    assert result["outcomes"] == {"passed": 3, "failed": 2}
    assert result["flips"] == 2
    # executed timeline is run 0, 2, 3, 4, 5 -> the second executed run is 2
    assert result["first_flip_run"] == 2


def test_outcome_counts_omit_zero_entries():
    history = [{"a": "passed"}, {"a": "failed"}, {"a": "skipped"}]
    outcomes = detect_flaky(history)["a"]["outcomes"]
    assert outcomes == {"passed": 1, "failed": 1}
    assert all(count > 0 for count in outcomes.values())


def test_history_is_not_mutated():
    history = [{"a": "passed"}, {"a": "failed"}]
    snapshot = [dict(run) for run in history]
    detect_flaky(history)
    assert history == snapshot


def test_larger_mixed_history():
    history = [
        {"fast": "passed", "slow": "failed", "skip": "skipped"},
        {"fast": "failed", "slow": "failed", "skip": "passed"},
        {"fast": "skipped", "slow": "passed", "skip": "skipped"},
        {"fast": "failed", "slow": "failed"},
        {"fast": "passed", "slow": "failed", "skip": "failed"},
    ]
    result = detect_flaky(history)
    assert set(result) == {"fast", "slow", "skip"}
    # fast: passed, failed, (skipped), failed, passed  -> 2 flips
    assert result["fast"] == {
        "outcomes": {"passed": 2, "failed": 2},
        "flips": 2,
        "first_flip_run": 1,
    }
    # slow: failed, failed, passed, failed, failed  -> 2 flips
    assert result["slow"] == {
        "outcomes": {"passed": 1, "failed": 4},
        "flips": 2,
        "first_flip_run": 1,
    }
    # skip: (skipped), passed, (skipped), (absent), failed  -> 1 flip
    assert result["skip"] == {
        "outcomes": {"passed": 1, "failed": 1},
        "flips": 1,
        "first_flip_run": 4,
    }
