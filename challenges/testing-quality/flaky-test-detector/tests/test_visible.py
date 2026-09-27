"""Visible tests — the learner sees these before submitting."""

from solution import detect_flaky


def test_detects_a_simple_flake():
    history = [{"a": "passed"}, {"a": "failed"}, {"a": "passed"}]
    assert detect_flaky(history) == {
        "a": {"outcomes": {"passed": 2, "failed": 1}, "flips": 2, "first_flip_run": 1}
    }


def test_ignores_stable_tests():
    history = [
        {"stable": "passed", "other": "failed"},
        {"stable": "passed", "other": "failed"},
    ]
    assert detect_flaky(history) == {}


def test_empty_history():
    assert detect_flaky([]) == {}


def test_reports_every_flaky_test():
    history = [{"a": "passed", "b": "failed"}, {"a": "failed", "b": "passed"}]
    result = detect_flaky(history)
    assert set(result) == {"a", "b"}
    assert result["a"]["outcomes"] == {"passed": 1, "failed": 1}
